"""panel — the chat.

Layout: a slim context line (document + agent state), the transcript, and a
rounded composer with one round send button. Styled from style.py's tokens so
it follows the app's light/dark mode; the shell (shell.py) mounts it as the
Chat page of the left sidebar.

All widget work happens on the main thread; workers reach it via signals.

PUBLIC HOOKS, relied on by other modules. Do not rename or change these
signatures without telling the callers:

    AgentPanel.show_notice(title, body, actions=None) -> Notice
        Renders a designed Notice in the transcript. `actions` is a list of
        (label, callable). Never renders a traceback.
    AgentPanel.set_backend_state(state)
        state in {'offline','idle','working'}. Drives the status dot.
    AgentPanel.add_shot(path, caption) -> Shot
        Inline viewport capture with a timestamp caption.
    AgentPanel.ask(text) -> bool
        Send `text` as a chat turn, as if typed (vision.ask_in_chat, R36).
    AgentPanel.new_chat() -> bool
        Clear the transcript and start a fresh chat for the active document
        (R70). Bodies already built stay in the document.

NO RAW EXCEPTION EVER REACHES THIS PANEL. Exception text goes to
FreeCAD.Console.PrintLog(); the user gets a Notice with a next step.
"""
import copy
import functools
import hashlib
import json
import os
import re
import shutil
import time
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

from . import build, client, engine, settings as cfgmod, style

PAD = 16

BACKEND_STATES = {
    # state: (label, token for the dot)
    "offline": ("Agent offline", "fail"),
    "idle": ("Agent ready", "ok"),
    "working": ("Working…", "accent"),
    "checking": ("Checking…", "dim"),
}

# Worker threads are created with parent=None and held here until they have
# finished (R19). A thread parented to a widget is destroyed with it -
# MEASURED: "QThread: Destroyed while thread is still running" and a core
# dump when the sidebar was torn down mid-turn.
_WORKERS = set()


def _keep_alive(thread):
    _WORKERS.add(thread)

    def _drop():
        try:
            # `finished` fires just before the thread stops (see
            # ClaudeRun._release): give it a moment rather than leak it.
            if thread.isRunning():
                thread.wait(1000)
            if not thread.isRunning():
                _WORKERS.discard(thread)
        except RuntimeError:
            _WORKERS.discard(thread)
    thread.finished.connect(_drop)
    return thread


def _error_summary(err):
    """One line for the build card: the exception line of a traceback.

    The full traceback goes to the agent and the Report view (R26)."""
    lines = [ln.strip() for ln in (err or "").strip().splitlines()
             if ln.strip()]
    if not lines:
        return "The script failed."
    for ln in reversed(lines):
        if not ln.startswith(("File ", "Traceback", "^", "~")):
            return ln if len(ln) <= 160 else ln[:159] + "…"
    return lines[-1][:160]

PANEL_QSS = """
#AgentPanel {{ background: {panel}; }}
#AgentPanel QLabel {{ font-family: {UI}; }}

#Context {{ background: {panel}; }}
#DocName {{ color: {text}; font-size: 13px; font-weight: 600; }}
#DocMeta {{ color: {dim}; font-size: 11px; }}
#StateText {{ color: {muted}; font-size: 11px; }}

#Stream, #StreamInner {{ background: {panel}; border: none; }}
#Stream QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
#Stream QScrollBar::handle:vertical {{ background: {line_strong}; border-radius: 3px; min-height: 30px; }}
#Stream QScrollBar::add-line, #Stream QScrollBar::sub-line {{ height: 0; width: 0; }}
#Stream QScrollBar::add-page, #Stream QScrollBar::sub-page {{ background: transparent; }}
#Stream QScrollBar:horizontal {{ height: 0; }}

#UserBubble {{
    background: {bubble}; color: {text}; font-size: 13px;
    border-radius: 16px; border-top-right-radius: 4px; padding: 9px 14px;
}}
#AgentText {{ color: {text}; font-size: 13px; }}
#Stamp {{ color: {dim}; font-size: 10px; }}

#ToolCard {{ background: {card}; border: 1px solid {line}; border-radius: 12px; }}
#ToolName {{ color: {text}; font-size: 12px; font-weight: 600; }}
#ToolArgs {{ color: {dim}; font-size: 11px; }}
/* QLabel#... matches '#AgentPanel QLabel' specificity (1,0,1), so the mono
   face wins by source order. MEASURED: as bare '#ToolBody' the panel-wide
   UI font outranked it and the measurement columns rendered proportional. */
QLabel#ToolBody {{ color: {muted}; font-family: {MONO}; font-size: 11px; }}
#ToolProse {{ color: {muted}; font-size: 12px; }}
#ToolWarn {{ color: {warn}; font-size: 12px; }}
/* R186: an explanation (work in progress, a check that could not confirm)
   is a muted note, not a warning. */
#ToolInfo {{ color: {muted}; font-size: 12px; }}
#StatusRun, #StatusOk, #StatusFail, #StatusIdle {{
    font-size: 10px; font-weight: 600; border-radius: 8px; padding: 2px 8px;
}}
#StatusRun  {{ color: {accent}; background: {hover}; }}
#StatusOk   {{ color: {ok}; background: {hover}; }}
#StatusFail {{ color: {fail}; background: {hover}; }}
#StatusIdle {{ color: {muted}; background: {hover}; }}
QLabel#ShotCap {{ color: {dim}; font-family: {MONO}; font-size: 10px; }}

#Notice {{ background: {card}; border: 1px solid {line}; border-radius: 14px; }}
#NoticeTitle {{ color: {text}; font-size: 13px; font-weight: 600; }}
#NoticeBody {{ color: {muted}; font-size: 12px; }}
QLabel#ErrDetail {{ color: {dim}; font-family: {MONO}; font-size: 10px; }}
#NoticeBtn, #ChipBtn {{
    background: {panel}; color: {text}; border: 1px solid {line};
    border-radius: 13px; padding: 0 13px; font-size: 12px; font-family: {UI};
    min-height: 26px; max-height: 26px;
}}
#NoticeBtn:hover, #ChipBtn:hover {{ background: {hover}; border-color: {line_strong}; }}
#NoticeBtn[primary="true"] {{ background: {btn_bg}; color: {btn_text}; border: none; font-weight: 600; }}
#NoticeBtn[primary="true"]:hover {{ background: {btn_bg_hover}; }}
/* R203 (D23 residue): a disabled button reads as disabled - the same
   tokens as #SendBtn:disabled - also when it is the filled primary one. */
#NoticeBtn:disabled, #ChipBtn:disabled {{ color: {dim}; }}
#NoticeBtn[primary="true"]:disabled {{ background: {line_strong}; color: {dim}; }}

#Hello {{ color: {text}; font-size: 22px; font-weight: 600; }}
#HelloSub {{ color: {muted}; font-size: 13px; }}
#Suggest {{
    background: {panel}; color: {text}; border: 1px solid {line};
    border-radius: 12px; padding: 0; font-size: 12px; text-align: left;
    font-family: {UI};
}}
#Suggest:hover {{ background: {hover}; border-color: {line_strong}; }}
QLabel#SuggestText {{ color: {text}; font-size: 12px; background: transparent; }}
#SectionLabel {{ color: {dim}; font-size: 10px; font-weight: 600; letter-spacing: 1px; }}

#ComposerWrap {{ background: {panel}; }}
#Composer {{ background: {composer}; border: 1px solid {line}; border-radius: 18px; }}
#Composer[focus="true"] {{ border-color: {line_strong}; }}
#Input {{
    background: transparent; border: none; color: {text};
    font-family: {UI}; font-size: 13px; padding: 0; selection-background-color: {line_strong};
}}
#SendBtn {{ background: {btn_bg}; border: none; border-radius: 15px; }}
#SendBtn:hover {{ background: {btn_bg_hover}; }}
#SendBtn:disabled {{ background: {line_strong}; }}
#GhostBtn {{
    background: transparent; color: {muted}; border: none; border-radius: 12px;
    padding: 4px 9px; font-size: 11px; font-family: {UI};
}}
#GhostBtn:hover {{ background: {hover}; color: {text}; }}
#Hint {{ color: {warn}; font-size: 11px; }}
"""


def _log(msg):
    """Implementation detail goes to the report view, never to the panel."""
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[AcadAgent] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def _hostport(base):
    """'http://127.0.0.1:4096' -> '127.0.0.1:4096'. Derived, never typed."""
    return base.split("//")[-1].rstrip("/")


def FreeCAD_doc_obj(doc_name, name):
    try:
        import FreeCAD
        return FreeCAD.getDocument(doc_name).getObject(name)
    except Exception:                                  # noqa: BLE001
        return None


def _repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


def _logo_label(height):
    """The Atech mark as a label that restyle() can repaint (R53: a mark
    rendered once in light mode stayed dark-on-dark after a theme flip)."""
    mark = QtWidgets.QLabel()
    mark.setObjectName("LogoMark")
    mark.setProperty("logo_h", int(height))
    pm = style.logo_pixmap(height)
    if pm is not None:
        mark.setPixmap(pm)
    return mark


def _plural(n, word):
    """'1 object', '2 objects' (R77)."""
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _is_model_object(o):
    """What the context line counts: solid-bearing features and seated
    Atech modules (Mesh::Feature, which have no Shape) - R77."""
    try:
        if getattr(o, "TypeId", "") == "Mesh::Feature":
            return True
        return hasattr(o, "Shape")
    except Exception:                                  # noqa: BLE001
        return False


_TB = "Traceback (most recent call last):"


def _model_line(err):
    """'model.py line 7' from the innermost frame of the agent's script, or
    "" when no frame names it. Install paths never leave this function."""
    import re
    hits = re.findall(r'File "([^"]*)", line (\d+)', err or "")
    for fname, line in reversed(hits):
        base = os.path.basename(fname)
        if base == "model.py" or fname == "<agent>":
            return "model.py line %s" % line
    return ""


def _card_error(err):
    """The build card's one line (R74): the model.py line + the exception,
    nothing else - no runner.py frames, no install paths."""
    where = _model_line(err)
    summary = _error_summary(err)
    return "%s: %s" % (where, summary) if where else summary


def _fix_report(err, limit=1500):
    """The fix message for the agent (R74): the traceback head and the
    exception FIRST, then what the script printed before it, truncated.
    The old message was err[-3000:], which could begin inside a huge print
    and never reach the traceback. Local stand-in for build.fix_report
    (WS-BUILD, S13); that one is used when it exists."""
    err = err or ""
    i = err.find(_TB)
    out, tb = (err[:i], err[i:]) if i >= 0 else ("", err)
    tb = tb.strip()
    exc = _error_summary(tb)
    body = tb
    budget = max(400, limit - len(exc) - 200)
    if len(body) > budget:
        lines = body.splitlines()
        head, tail = lines[:4], lines[-8:]
        body = "\n".join(head + ["  ..."] + tail)
        if len(body) > budget:
            body = body[:budget // 2] + "\n  ...\n" + body[-budget // 2:]
    msg = "%s\n%s" % (exc, body) if exc and exc not in body[:len(exc) + 1] \
        else body
    out = out.strip()
    room = limit - len(msg) - 60
    if out and room > 80:
        if len(out) > room:
            out = "..." + out[-room:]
        msg += "\n\nPrinted before the error (truncated):\n" + out
    return msg[:limit]


class Dot(QtWidgets.QWidget):
    """An 8 px status dot. Painted, so its colour is exact in both modes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._c = QtGui.QColor("#999999")

    def set_color(self, hexc):
        self._c = QtGui.QColor(hexc)
        self.update()

    def paintEvent(self, _ev):                         # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(self._c)
        p.drawEllipse(0, 0, 8, 8)


# ----------------------------------------------------------------- blocks
#: R201/R216: how a failed (or refused) tool row starts on a card.
FAILED_ROW = "✗ "


def _is_failed_row(line):
    """R205: a row mark_failed drew (" · failed: " / " · refused: ")."""
    return line.startswith(FAILED_ROW) and (
        " · failed: " in line or " · refused: " in line)


class _BodyLabel(QtWidgets.QLabel):
    """A card body whose failed rows are drawn in the theme's failure
    colour (R205: a failure must be louder than a pass, R5).

    text() is always the plain text the card holds - every caller (the
    transcript snapshot, append, mark_failed, tests) reads lines from it.
    Only when a row is a failed one (see _is_failed_row) is the label
    rendered as rich text, the other rows keeping the label's own colour;
    render() draws it again after a theme flip. Deciding from the text
    itself means a card restored from a kept transcript (R190) is drawn
    the same way with no extra state."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._plain = ""
        self.setText(text)

    def text(self):                                    # noqa: D401
        return self._plain

    def setText(self, text):                           # noqa: N802
        self._plain = text or ""
        self.render()

    def has_failed_rows(self):
        return any(_is_failed_row(ln) for ln in self._plain.split("\n"))

    def render(self):
        if not self.has_failed_rows():
            QtWidgets.QLabel.setTextFormat(self, QtCore.Qt.PlainText)
            QtWidgets.QLabel.setText(self, self._plain)
            return
        import html
        fail = style.tokens().get("fail", "#cc3d28")
        rows = []
        for ln in self._plain.split("\n"):
            e = html.escape(ln)
            rows.append('<span style="color:%s">%s</span>' % (fail, e)
                        if _is_failed_row(ln) else e)
        QtWidgets.QLabel.setTextFormat(self, QtCore.Qt.RichText)
        # pre-wrap keeps the mono columns' runs of spaces and still wraps
        # a prose body (setWordWrap decides whether it may).
        QtWidgets.QLabel.setText(
            self, '<div style="white-space:pre-wrap">%s</div>'
            % "<br>".join(rows))


class ToolCard(QtWidgets.QFrame):
    """One tool call: name, args, status, measured result.

    Never collapsed by default (R3) - the point of the product is that you
    can read what the agent actually did. mono=True keeps a measurement
    table's columns aligned; mono=False is prose and wraps.
    """

    def __init__(self, name, args="", parent=None, mono=True):
        super().__init__(parent)
        self.setObjectName("ToolCard")
        self.spec = (name, args, mono)     # R190: how to draw it again
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)

        head = QtWidgets.QHBoxLayout()
        head.setSpacing(8)
        lbl = QtWidgets.QLabel(name)
        lbl.setObjectName("ToolName")
        head.addWidget(lbl)
        if args:
            a = QtWidgets.QLabel(args)
            a.setObjectName("ToolArgs")
            a.setMinimumWidth(10)
            a.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                            QtWidgets.QSizePolicy.Preferred)
            head.addWidget(a, 1)
        else:
            head.addStretch(1)
        self.status = QtWidgets.QLabel("working")
        self.status.setObjectName("StatusRun")
        head.addWidget(self.status)
        lay.addLayout(head)

        # S19: one live line - the text streaming in, or "writing model.py:
        # N lines" - replaced in place, never appended.
        self.progress = QtWidgets.QLabel("")
        self.progress.setObjectName("ToolArgs")
        self.progress.setTextFormat(QtCore.Qt.PlainText)
        self.progress.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                                    QtWidgets.QSizePolicy.Preferred)
        self.progress.setMinimumWidth(10)
        self.progress.hide()
        lay.addWidget(self.progress)

        # R205: its own label class, so a failed row is drawn in the
        # failure colour; text() stays the plain lines.
        self.body = _BodyLabel("")
        self.body.setObjectName("ToolBody" if mono else "ToolProse")
        self.body.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.body.setWordWrap(not mono)
        if mono:
            # An unwrapped mono line must clip inside its card, never widen
            # the transcript. MEASURED: a 60-char build line pushed the whole
            # stream past the panel edge and clipped every message.
            self.body.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                                    QtWidgets.QSizePolicy.Preferred)
            self.body.setMinimumWidth(10)
        self.body.hide()
        lay.addWidget(self.body)

        # R127: one wrapped sentence the user must read (the no-bwrap
        # caveat). Not in the mono body, which clips instead of wrapping,
        # and not cleared with it: a later preview of the same turn keeps it.
        self.note = QtWidgets.QLabel("")
        # R146: a caveat reads as one - the theme's warning colour, not the
        # muted prose colour of the card's other lines.
        self.note.setObjectName("ToolWarn")
        self.note.setTextFormat(QtCore.Qt.PlainText)
        self.note.setWordWrap(True)
        self.note.hide()
        self.note_text = ""
        self.caveat = ""          # the R127 caveat, kept for the turn
        self.caveat_text = ""     # what the note shows as a warning
        self.info_text = ""       # ... and as a muted explanation (R186)
        lay.addWidget(self.note)

        # R184: the stall line - no stream event for a while - with a way
        # to retry. Hidden until the watchdog speaks; the next event hides
        # it again. The run itself is never killed from here.
        self.stall_row = QtWidgets.QWidget()
        sl = QtWidgets.QHBoxLayout(self.stall_row)
        sl.setContentsMargins(0, 2, 0, 0)
        sl.setSpacing(8)
        self.stall = QtWidgets.QLabel("")
        self.stall.setObjectName("ToolInfo")
        self.stall.setTextFormat(QtCore.Qt.PlainText)
        self.stall.setWordWrap(True)
        self.stall.setMinimumWidth(10)
        sl.addWidget(self.stall, 1)
        self.stall_btn = QtWidgets.QPushButton("Retry")
        self.stall_btn.setObjectName("NoticeBtn")
        self.stall_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.stall_btn.setToolTip("Stop this reply and send the message "
                                  "again, in the same conversation")
        self.stall_btn.clicked.connect(self._on_stall_btn)
        sl.addWidget(self.stall_btn, 0, QtCore.Qt.AlignTop)
        # R198/R201: Stop beside it - and alone, when the silence is the
        # model still working on an open message (a Retry would throw its
        # reasoning away).
        self.stall_stop = QtWidgets.QPushButton("Stop")
        self.stall_stop.setObjectName("NoticeBtn")
        self.stall_stop.setCursor(QtCore.Qt.PointingHandCursor)
        self.stall_stop.setToolTip("Stop this reply")
        self.stall_stop.clicked.connect(self._on_stall_stop)
        sl.addWidget(self.stall_stop, 0, QtCore.Qt.AlignTop)
        self.stall_row.hide()
        self._stall_fn = None
        self._stall_stop_fn = None
        lay.addWidget(self.stall_row)

    def set_note(self, text):
        """The card's caveat line (R127) in the warning style; "" hides
        it. Keeps whatever explanation set_notes() gave the card."""
        self.set_notes(text, self.info_text)

    def set_notes(self, caveat="", info=""):
        """R186: one wrapped note, two voices. `caveat` (R127, the no-bwrap
        warning) is drawn as a warning with its sign; `info` (the R174
        in-progress explanation, R191's "could not confirm") in the muted
        note colour, never as a warning. "" for both hides the note."""
        caveat, info = caveat or "", info or ""
        self.caveat_text, self.info_text = caveat, info
        self.note_text = "\n".join(t for t in (caveat, info) if t)
        self.note.setObjectName("ToolWarn" if caveat else "ToolInfo")
        _repolish(self.note)
        if caveat and info:
            # Both at once: the label is the warning; the explanation keeps
            # the muted colour inside it (read from the theme now; the
            # panel's restyle() renders it again on a theme flip).
            import html
            muted = style.tokens().get("muted", "#888888")
            self.note.setTextFormat(QtCore.Qt.RichText)
            self.note.setText(
                "%s<br><span style=\"color:%s\">%s</span>" % (
                    html.escape("⚠ " + caveat).replace("\n", "<br>"), muted,
                    html.escape(info).replace("\n", "<br>")))
        else:
            self.note.setTextFormat(QtCore.Qt.PlainText)
            self.note.setText(("⚠ " + caveat) if caveat else info)
        self.note.setVisible(bool(self.note_text))

    def set_stall(self, text, action=None, stop=None):
        """R184: the waiting line, its Retry (`action`) and Stop (`stop`,
        R198/R201); "" hides all of them."""
        self.stall.setText(text or "")
        self._stall_fn = action if text else None
        self._stall_stop_fn = stop if text else None
        self.stall_btn.setVisible(bool(text) and action is not None)
        self.stall_stop.setVisible(bool(text) and stop is not None)
        self.stall_row.setVisible(bool(text))

    def _on_stall_stop(self):
        fn = self._stall_stop_fn
        if fn is not None:
            fn()

    def mark_failed(self, line, reason, verb="failed"):
        """R201 (D76): the row `line` (a tool call as _on_claude_tool drew
        it) failed: it is redrawn as failed with a short reason, so the
        last row no longer reads as the step in progress. Appended when the
        row has already scrolled off the card. R205: drawn in the failure
        colour (_BodyLabel). R216: verb="refused" for a call the CLI
        refused for want of a permission (it never ran)."""
        cur = self.body.text()
        lines = cur.split("\n") if cur else []
        new = "%s%s · %s: %s" % (FAILED_ROW, line.rstrip(), verb,
                                 reason or "error")
        for i in range(len(lines) - 1, -1, -1):
            if lines[i] == line:
                lines[i] = new
                break
        else:
            lines.append(new)
        self.body.setText("\n".join(lines))
        self.body.show()

    def stall_text(self):
        return self.stall.text() if not self.stall_row.isHidden() else ""

    def _on_stall_btn(self):
        fn = self._stall_fn
        if fn is not None:
            fn()

    def set_progress(self, text):
        """The live line (S19); "" hides it."""
        self.progress.setText(text or "")
        self.progress.setVisible(bool(text))

    def clear(self):
        """Empty the body: one card updated in place (R76)."""
        self.body.setText("")
        self.body.hide()

    def append(self, text, keep=None):
        cur = self.body.text()
        lines = ((cur + "\n" + text) if cur else text).split("\n")
        if keep and len(lines) > keep:
            lines = lines[-keep:]
        self.body.setText("\n".join(lines))
        self.body.show()

    def set_status(self, text, kind):
        """kind: run | ok | fail | idle. A failure must be louder than a
        pass (R5) - and 'nothing to measure' is not a failure."""
        self.status.setText(text)
        self.status.setObjectName({"run": "StatusRun", "ok": "StatusOk",
                                   "fail": "StatusFail",
                                   "idle": "StatusIdle"}[kind])
        _repolish(self.status)


class Notice(QtWidgets.QFrame):
    """A designed system message: title, body, optional action buttons.

    This is what the user sees instead of a traceback. The first action is
    the primary one and is drawn filled.
    """

    def __init__(self, title, body, actions=None, detail=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Notice")
        # R190: the notice as data - its actions included - so a document's
        # kept chat can draw it again after a tab switch.
        self.spec = (title, body, list(actions or ()), detail)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        t = QtWidgets.QLabel(title)
        t.setObjectName("NoticeTitle")
        t.setWordWrap(True)
        lay.addWidget(t)

        b = QtWidgets.QLabel(body)
        b.setObjectName("NoticeBody")
        b.setWordWrap(True)
        b.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        lay.addWidget(b)

        self.detail = None
        if detail:
            # Raw text (a CLI message, an error) is collapsed behind a
            # "Details" button: available, never the headline (R21).
            d = QtWidgets.QLabel(detail)
            d.setObjectName("ErrDetail")
            d.setWordWrap(True)
            d.setTextFormat(QtCore.Qt.PlainText)
            d.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            d.hide()
            lay.addWidget(d)
            self.detail = d

        self.buttons = []
        if actions or detail:
            lay.addSpacing(4)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)
            for i, (label, fn) in enumerate(actions or ()):
                btn = QtWidgets.QPushButton(label)
                btn.setObjectName("NoticeBtn")
                btn.setProperty("primary", i == 0)
                btn.setCursor(QtCore.Qt.PointingHandCursor)
                btn.clicked.connect(fn)
                row.addWidget(btn)
                self.buttons.append(btn)
            if detail:
                tog = QtWidgets.QPushButton("Details")
                tog.setObjectName("GhostBtn")
                tog.setCursor(QtCore.Qt.PointingHandCursor)
                tog.clicked.connect(self._toggle_detail)
                row.addWidget(tog)
                self._detail_btn = tog
            row.addStretch(1)
            lay.addLayout(row)

    def _toggle_detail(self):
        show = self.detail.isHidden()
        self.detail.setVisible(show)
        self._detail_btn.setText("Hide details" if show else "Details")


#: A GFM table: a pipe row followed by its delimiter row (|---|:--:|).
_MD_TABLE = re.compile(
    r"^[ \t]*\|?[^\n|]*\|[^\n]*\n"
    r"[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)+\|?[ \t]*$",
    re.M)


def has_md_table(text):
    """True when `text` holds a GitHub-flavoured Markdown table (R124)."""
    return bool(text) and bool(_MD_TABLE.search(str(text)))


#: Markdown an agent reply uses besides tables (R153, D61): **bold**,
#: __bold__, `code`, "# heading", "- item", "1. item".
_MD_MARKUP = re.compile(
    r"\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`"
    r"|^[ \t]{0,3}#{1,6}[ \t]+\S|^[ \t]*[-*+][ \t]+\S|^[ \t]*\d{1,3}[.)][ \t]+\S",
    re.M)


def has_markdown(text):
    """True when agent text carries Markdown worth rendering (R124, R153):
    a GFM table, or bold / code / headings / lists. Plain prose is not
    touched, so it keeps its line breaks exactly as written."""
    if not text:
        return False
    return has_md_table(text) or bool(_MD_MARKUP.search(str(text)))


_FENCE = re.compile(r"^[ \t]{0,3}(```|~~~)")


def md_hard_breaks(text):
    """Keep an agent's single line breaks when its reply is rendered as
    Markdown (R153). GFM joins "**Volume:** 12\\n**Mass:** 3" into one
    paragraph (a soft break is a space), so a reply that was shown line by
    line as plain text ran together once it had any bold. A line followed
    by another non-blank line gets a hard break, except inside code fences
    and around table rows (a table must stay a table).

    Qt's parser also needs a blank line between a table and the prose
    around it: measured, "Here:\\n| a | b |\\n|---|---|\\n| 1 | 2 |"
    rendered as one paragraph of raw pipes (0 tables). The blank line is
    added."""
    lines = str(text).split("\n")
    out, fence, table = [], False, False
    for i, ln in enumerate(lines):
        if _FENCE.match(ln):
            fence = not fence
            table = False
            out.append(ln)
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if not fence:
            if not table and "|" in ln and \
                    _MD_TABLE.match(ln + "\n" + nxt):
                table = True
                if out and out[-1].strip():
                    out.append("")
            elif table and "|" not in ln:
                table = False
                if ln.strip():
                    out.append("")
        if not fence and ln.strip() and nxt.strip() and \
                "|" not in ln and "|" not in nxt and \
                not _FENCE.match(nxt) and \
                not ln.endswith(("  ", "\\")):
            ln += "  "
        out.append(ln)
    return "\n".join(out)


_BODY_STYLE = re.compile(r"(<body)\s+style=\"[^\"]*\"", re.I)


def md_table_html(text):
    """Agent Markdown (with a table) as rich text for a QLabel (R124).

    Not Qt.MarkdownText: QLabel parses that with raw HTML ENABLED, so an
    agent's "the <port> argument" swallowed everything after the "<" -
    measured: "Use the <port> field ... | a | b |" rendered as "Use the"
    and nothing else, table included. QTextDocument with MarkdownNoHTML
    keeps such text literal; the document's own body font is dropped so
    the label's QSS font still applies."""
    doc = QtGui.QTextDocument()
    feats = QtGui.QTextDocument.MarkdownFeature(
        QtGui.QTextDocument.MarkdownDialectGitHub.value
        | QtGui.QTextDocument.MarkdownNoHTML.value)
    doc.setMarkdown(str(text), feats)
    html = _BODY_STYLE.sub(r"\1", doc.toHtml(), count=1)
    # Links come out hard-coded #0000ff, unreadable in the dark theme: the
    # label's palette link colour applies instead.
    return html.replace(" color:#0000ff;", "").replace("color:#0000ff;", "")


class Bubble(QtWidgets.QWidget):
    """User text sits right in a soft bubble; agent text is plain prose with
    the mark beside it - the same split the atech.dev project chat uses."""

    def __init__(self, text, role, parent=None):
        super().__init__(parent)
        self.raw_text, self.role = text, role     # R190: kept per document
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self._cap = None
        if role == "user":
            lbl.setObjectName("UserBubble")
            lbl.setTextFormat(QtCore.Qt.PlainText)
            lay.addStretch(1)
            lay.addWidget(lbl, 0, QtCore.Qt.AlignRight)
            # A word-wrapped QLabel in a stretched row collapses to its
            # narrowest wrap. Size it from the text: one line if it fits,
            # otherwise the full 290 px measure.
            # Measured with the bubble's styled font (13 px), not the label's
            # pre-stylesheet default, which under-reported and wrapped early.
            f = QtGui.QFont(style.FONT_UI)
            f.setPixelSize(13)
            natural = QtGui.QFontMetrics(f).horizontalAdvance(text) + 34
            # R142: never wider than the transcript. A fixed 290 px was
            # wider than the 292 px transcript less its margins at 900x600;
            # resizeEvent narrows the label to the row it is given.
            self._cap = min(290, max(40, natural))
            lbl.setFixedWidth(self._cap)
        else:
            lbl.setObjectName("AgentText")
            if has_markdown(text):
                # R124 (D47): the agent answers with GFM tables; shown as
                # plain text they were raw pipes. R153 (D61): the same for
                # **bold**, lists and headings - the "Ask about this view"
                # answer is a chat reply and showed raw asterisks. Rendered
                # with QTextDocument's GitHub dialect, raw HTML off (see
                # md_table_html), in the label's own (QSS) font. Plain prose
                # keeps the format it always had.
                lbl.setTextFormat(QtCore.Qt.RichText)
                lbl.setText(md_table_html(md_hard_breaks(text)))
                self.markdown = True
            mark = _logo_label(14)
            mark.setFixedWidth(18)
            mark.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)
            lay.addWidget(mark, 0, QtCore.Qt.AlignTop)
            lay.addWidget(lbl, 1)
        self.label = lbl

    markdown = False        # the text was rendered from Markdown (R153)

    def minimumSizeHint(self):                         # noqa: N802
        # R142: a user bubble may shrink below its label's current width;
        # resizeEvent then narrows the label (and it wraps).
        hint = super().minimumSizeHint()
        if self._cap is None:
            return hint
        return QtCore.QSize(min(hint.width(), 40), hint.height())

    def resizeEvent(self, ev):                         # noqa: N802
        super().resizeEvent(ev)
        if self._cap is not None:
            w = min(self._cap, max(40, ev.size().width()))
            if w != self.label.width():
                self.label.setFixedWidth(w)


class SuggestButton(QtWidgets.QPushButton):
    """A "Try asking" card whose text WRAPS (R87). A QPushButton draws its
    text on one line, so at 900x600 the cards cut prompts mid-word; the text
    is a word-wrapped label inside it instead, and the button asks the label
    how tall it must be at its width. text() is the prompt, as before."""

    MARGINS = (12, 9, 12, 9)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setObjectName("Suggest")
        self._prompt = text
        lay = QtWidgets.QHBoxLayout(self)
        left, top, right, bottom = self.MARGINS
        lay.setContentsMargins(left + self.BORDER, top + self.BORDER,
                               right + self.BORDER, bottom + self.BORDER)
        self.label = QtWidgets.QLabel(text)
        self.label.setObjectName("SuggestText")
        self.label.setWordWrap(True)
        self.label.setTextFormat(QtCore.Qt.PlainText)
        self.label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.label)
        sp = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                   QtWidgets.QSizePolicy.Minimum)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.setMinimumWidth(40)

    def text(self):                                    # noqa: D401
        return self._prompt

    def hasHeightForWidth(self):                       # noqa: N802
        return True

    #: The 1 px QSS border on each side, which the inner layout does not
    #: know about. MEASURED: without it a two-line card at 320 px was 1 px
    #: shorter than its label needed.
    BORDER = 1

    def heightForWidth(self, w):                       # noqa: N802
        left, top, right, bottom = self.MARGINS
        inner = max(10, w - left - right - 2 * self.BORDER)
        return self.label.heightForWidth(inner) + top + bottom + \
            2 * self.BORDER

    def sizeHint(self):                                # noqa: N802
        left, _t, right, _b = self.MARGINS
        w = self.width() if self.width() > 40 else \
            self.label.sizeHint().width() + left + right + 2 * self.BORDER
        return QtCore.QSize(w, self.heightForWidth(w))

    def minimumSizeHint(self):                         # noqa: N802
        return QtCore.QSize(40, self.heightForWidth(max(self.width(), 40)))

    def resizeEvent(self, ev):                         # noqa: N802
        super().resizeEvent(ev)
        if ev.size().width() != ev.oldSize().width():
            self.updateGeometry()       # the height follows the width


class Welcome(QtWidgets.QFrame):
    """What the chat shows before anyone has typed anything.

    R132: it FITS the transcript it sits in. At 900x600 the sidebar leaves
    about 300 px above the composer and the full Welcome is taller, so the
    last "Try asking" card was cut off at the composer. fit(avail, width)
    first drops the logo and tightens the spacing, then the trailing
    examples, until the rest fits; at least one example always stays. It
    starts from the full layout every time, so a taller window brings
    everything back."""

    picked = QtCore.Signal(str)

    #: (top margin, logo gap, gap before TRY ASKING) - full, then compact.
    FULL = (18, 14, 26)
    COMPACT = (4, 0, 14)

    def __init__(self, title, body, prompts=(), actions=(), parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, self.FULL[0], 0, 8)
        lay.setSpacing(0)
        self._lay = lay

        self._mark = _logo_label(28)
        lay.addWidget(self._mark)
        self._mark_gap = QtWidgets.QSpacerItem(0, self.FULL[1])
        lay.addSpacerItem(self._mark_gap)

        t = QtWidgets.QLabel(title)
        t.setObjectName("Hello")
        t.setWordWrap(True)
        lay.addWidget(t)
        self.title = t
        lay.addSpacing(6)
        b = QtWidgets.QLabel(body)
        b.setObjectName("HelloSub")
        b.setWordWrap(True)
        lay.addWidget(b)
        self.sub = b

        if actions:
            lay.addSpacing(16)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)
            for i, (label, fn) in enumerate(actions):
                btn = QtWidgets.QPushButton(label)
                btn.setObjectName("NoticeBtn")
                btn.setProperty("primary", i == 0)
                btn.setCursor(QtCore.Qt.PointingHandCursor)
                btn.clicked.connect(fn)
                row.addWidget(btn)
            row.addStretch(1)
            lay.addLayout(row)

        self.rows = []
        self._sec_gap = None
        self._sec = None
        self._rows_lay = None
        if prompts:
            self._sec_gap = QtWidgets.QSpacerItem(0, self.FULL[2])
            lay.addSpacerItem(self._sec_gap)
            sec = QtWidgets.QLabel("TRY ASKING")
            sec.setObjectName("SectionLabel")
            lay.addWidget(sec)
            self._sec = sec
            self._sec_after = QtWidgets.QSpacerItem(0, 8)
            lay.addSpacerItem(self._sec_after)
            # Their own layout: a hidden card takes its spacing with it.
            rows = QtWidgets.QVBoxLayout()
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setSpacing(6)
            for ptxt in prompts:
                r = SuggestButton(ptxt)
                r.setCursor(QtCore.Qt.PointingHandCursor)
                r.clicked.connect(lambda _=False, s=ptxt: self.picked.emit(s))
                self.rows.append(r)
                rows.addWidget(r)
            lay.addLayout(rows)
            self._rows_lay = rows
        self.compact = False

    def _set_compact(self, on):
        top, logo, sec = self.COMPACT if on else self.FULL
        m = self._lay.contentsMargins()
        self._lay.setContentsMargins(m.left(), top, m.right(), m.bottom())
        self._mark.setVisible(not on)
        self._mark_gap.changeSize(0, logo)
        if self._sec_gap is not None:
            self._sec_gap.changeSize(0, sec)
        self.compact = bool(on)
        self._lay.invalidate()

    def _set_section(self, on):
        """Show or hide the TRY ASKING heading with its gaps (R143)."""
        if self._sec is None:
            return
        self._sec.setVisible(on)
        self._sec_after.changeSize(0, 8 if on else 0)
        if not on:
            self._sec_gap.changeSize(0, 0)
        self._lay.invalidate()

    def height_at(self, width):
        """The height this Welcome needs at `width`, as laid out now.
        The examples' own layout is invalidated too: invalidating the outer
        one does not recurse, and a card hidden a moment ago still counted
        (MEASURED: 332 px with 3, 2 and 1 card shown)."""
        if self._rows_lay is not None:
            self._rows_lay.invalidate()
        self._lay.invalidate()
        if self._lay.hasHeightForWidth():
            return self._lay.totalHeightForWidth(int(width))
        return self._lay.totalSizeHint().height()

    def fit(self, avail, width, keep=1):
        """Fit in `avail` px at `width` (R132). At least `keep` examples
        stay (R143: 0 under an offline notice, whose examples cannot be
        sent); with none left the TRY ASKING heading goes too, and with
        keep=0 the explanatory line under the heading last (the notice
        below is what the user must reach). Returns how many examples are
        shown."""
        self._set_compact(False)
        for r in self.rows:
            r.setVisible(True)
        self.sub.setVisible(True)
        self._set_section(True)
        if self.height_at(width) > avail:
            self._set_compact(True)
            shown = list(self.rows)
            while len(shown) > keep and self.height_at(width) > avail:
                shown.pop().setVisible(False)
                if not shown:
                    self._set_section(False)
                    self.height_at(width)
            if keep == 0 and self.height_at(width) > avail:
                self.sub.setVisible(False)
        self.updateGeometry()
        return sum(1 for r in self.rows if not r.isHidden())


class FitPixmap(QtWidgets.QLabel):
    """A capture scaled to the width the chat gives it (R142).

    The old Shot scaled every capture to a fixed 330 px, which made the card
    at least 344 px wide; at 900x600 the transcript is 292 px wide, so the
    scroll content grew to 376 px (horizontal scrolling is off) and EVERY
    card lost 84 px on the right. This label asks only for its aspect ratio
    (height for width), never for a width, and rescales on resize. It never
    scales up past the capture's own pixels."""

    #: The width it asks for when nothing constrains it (the old size).
    HINT = 330

    def __init__(self, pix, parent=None):
        super().__init__(parent)
        self._src = pix
        self._shown_w = None
        self.setMinimumWidth(40)
        sp = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Ignored,
                                   QtWidgets.QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self._rescale(self.HINT)

    def _fit_w(self, w):
        return max(1, min(int(w), self._src.width()))

    def hasHeightForWidth(self):                       # noqa: N802
        return True

    def heightForWidth(self, w):                       # noqa: N802
        sw = self._fit_w(w)
        return max(1, int(round(self._src.height() * sw /
                                float(max(1, self._src.width())))))

    def sizeHint(self):                                # noqa: N802
        w = self._fit_w(self.HINT)
        return QtCore.QSize(w, self.heightForWidth(w))

    def minimumSizeHint(self):                         # noqa: N802
        return QtCore.QSize(40, self.heightForWidth(40))

    def shown_width(self):
        """The width of the pixmap on screen now (for tests)."""
        return self._shown_w

    def _rescale(self, w):
        sw = self._fit_w(w)
        if sw != self._shown_w:
            self._shown_w = sw
            self.setPixmap(self._src.scaledToWidth(
                sw, QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, ev):                         # noqa: N802
        super().resizeEvent(ev)
        if ev.size().width() != ev.oldSize().width():
            self._rescale(ev.size().width())


class Shot(QtWidgets.QFrame):
    """An inline viewport capture with a timestamp (R4). The image follows
    the chat's width (R142, FitPixmap)."""

    def __init__(self, path, caption, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolCard")
        self.spec = (path, caption)         # R190
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 8)
        lay.setSpacing(6)
        pix = QtGui.QPixmap(path)
        if not pix.isNull():
            img = FitPixmap(pix)
        else:
            img = QtWidgets.QLabel()
            img.setText("Capture could not be read.")
            img.setObjectName("ToolProse")
            _log("unreadable capture: %s" % path)
        lay.addWidget(img)
        self.image = img
        cap = QtWidgets.QLabel(caption)
        cap.setObjectName("ShotCap")
        cap.setContentsMargins(6, 0, 6, 0)
        cap.setWordWrap(True)
        lay.addWidget(cap)


class ScriptReview(QtWidgets.QDialog):
    """R98 (R11 follow-up): read the design script a file carries before it
    is allowed into the chat. Nothing runs from here; accepting only records
    the script as the user's own (build.trust_script)."""

    def __init__(self, script, objects=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review the design script")
        self.resize(640, 520)
        lay = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QLabel(
            "This document carries a design script that Atech Atelier did not "
            "write on this computer%s. Read it before you let the chat use "
            "it: it runs as Python on this computer at the next build." % (
                " (objects: %s)" % ", ".join(objects[:8]) if objects else ""))
        head.setWordWrap(True)
        lay.addWidget(head)
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        f = QtGui.QFont(style.FONT_MONO)
        f.setStyleHint(QtGui.QFont.Monospace)
        self.text.setFont(f)
        self.text.setPlainText(script or "")
        lay.addWidget(self.text, 1)
        box = QtWidgets.QDialogButtonBox()
        self.use_btn = box.addButton("Use this script",
                                     QtWidgets.QDialogButtonBox.AcceptRole)
        box.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


class HealthWorker(QtCore.QThread):
    """Mount-time reachability probe. Never blocks the GUI thread.
    Create with parent=None and _keep_alive() it (R19)."""

    done = QtCore.Signal(bool)

    def __init__(self, base, parent=None):
        super().__init__(parent)
        self.base = base
        self.owner = None       # R105: (kind, listener) when it answered
        self.refused = None     # R105: owner kind of a refused backend

    def run(self):
        ok = False
        try:
            ok = bool(client.Backend(self.base).health(timeout=3))
        except Exception as exc:                       # noqa: BLE001
            _log("health probe failed: %r" % (exc,))
            ok = False
        if ok:
            self.owner = self._owner(self.base)
            ok = not self._refuse(self.owner)
        self.done.emit(ok)

    def _refuse(self, owner):
        """R105: a backend another account runs is never used (the user's
        work would go to that account's process), and with
        ATECH_AGENT_ADOPT=0 none this Studio did not start is. Sets
        self.refused to the owner kind when so."""
        if not owner:
            return False
        try:
            from . import backend
            kind = owner[0]
            if kind == backend.OTHER_USER or (
                    kind != backend.OWN and not backend.adopt_allowed()):
                self.refused = kind
                _log("backend at %s refused: %s" % (self.base, kind))
                return True
        except Exception as exc:                       # noqa: BLE001
            _log("backend refusal: %r" % (exc,))
        return False

    @staticmethod
    def _owner(base):
        """R105: whose backend answered - (kind, listener record) for a
        loopback address, None elsewhere (a remote host has no /proc
        entry here to trace)."""
        try:
            from urllib.parse import urlsplit
            from . import backend
            u = urlsplit(base)
            if u.hostname not in ("127.0.0.1", "localhost", "::1"):
                return None
            info = backend.listener(u.port or 80)
            return backend.classify(info), info
        except Exception as exc:                       # noqa: BLE001
            _log("backend owner: %r" % (exc,))
            return None


class ClaudeProbe(QtCore.QThread):
    """Mount-time check that Claude Code can actually answer (R21, R22):
    find the binary (including the login-shell probe a desktop launch
    needs), then ask `claude auth status`. Off the GUI thread: both start
    processes. done(ok, kind, why): kind in {"", "missing", "auth"}."""

    done = QtCore.Signal(bool, str, str)

    def run(self):
        try:
            from . import claude_cli
            exe = claude_cli.locate()
            if exe is None:
                _ok, why = engine.available(engine.CLAUDE)
                self.done.emit(False, "missing", why)
                return
            logged_in, detail = claude_cli.auth_status()
            if logged_in is False:
                self.done.emit(False, "auth", detail)
                return
            # Warm the --help flag cache here, off the GUI thread, so the
            # first turn does not pay for it (S16).
            claude_cli.supported_flags(exe)
            # None = could not tell. Not a failure we can name; the first
            # turn will say what is wrong, classified.
            self.done.emit(True, "", "")
        except Exception as exc:                       # noqa: BLE001
            _log("claude probe failed: %r" % (exc,))
            self.done.emit(True, "", "")


class ChatState(object):
    """One document's chat: its workspace, last good build and Claude
    session (R17). Keyed by the document's Uid in AgentPanel._docs."""

    def __init__(self, key, doc_name, ws, prev=None):
        self.key = key              # doc.Uid, or NO_DOC until a build lands
        self.doc_name = doc_name    # FreeCAD document Name at send time
        self.ws = ws
        self.prev = prev            # build.Result.record() of the last good build
        self.sid = None             # Claude Code session id
        self.framed = False
        # R94/D50: the camera has turned to the Atech module face once.
        self.faced = False
        # sha1 of the model.py last built WITHOUT a failure (S02). Only that
        # script may be treated as "already built"; a script that failed
        # must be rebuilt even when rewritten byte for byte.
        self.good_hash = None
        # (sha1, fix message) of the script whose FINAL build failed: a fix
        # turn that leaves it unchanged has not fixed anything (R98/R75).
        self.failed = None
        # R191: the intent.json misses of that failed build when they were
        # its ONLY failures (else None).
        self.failed_intent = None
        self.review_offered = False     # R98: the untrusted-script notice
        # R113: objects of a still-untrusted script, carried into a new chat
        # of the same document (new_chat drops prev, which held the flag).
        self.untrusted = None
        # R200 (D75): a new chat on a document the agent already built
        # into adopts that design on its first turn.
        self.adopt_on_first_turn = False


NO_DOC = "__no_document__"

#: Notices about the sample crane failing to load; removed once a crane
#: document is open after all (R54).
CRANE_NOTICE_TITLES = ("Sample crane not available",
                       "Could not open the sample crane",
                       "Could not open the reference model")


# ------------------------------------------------ session store (S07)
def sessions_path():
    """{doc Uid: {ws, sid, prev}} across restarts, next to the chat
    workspaces in the user data dir."""
    return os.path.join(cfgmod.chat_workspace_root(), "sessions.json")


def load_sessions(path=None):
    try:
        with open(path or sessions_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_session(key, state, path=None):
    """Persist (or with state=None, forget) one document's chat. Only real
    document Uids are stored. Never raises: a lost record only costs the
    next session its --resume."""
    if not key or key == NO_DOC:
        return False
    path = path or sessions_path()
    data = load_sessions(path)
    if state is None:
        if data.pop(key, None) is None:
            return True
    else:
        data[key] = {"ws": state.ws, "sid": state.sid, "prev": state.prev,
                     "doc": state.doc_name, "saved": int(time.time())}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        _log("session store: %r" % (exc,))
        return False


class PromptEdit(QtWidgets.QPlainTextEdit):
    """Multi-line input that grows to 6 lines. Enter sends, Shift+Enter
    breaks the line."""

    submit = QtCore.Signal()
    focused = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Input")
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.document().setDocumentMargin(2)
        self.textChanged.connect(self._fit)
        self._fit()

    def keyPressEvent(self, ev):                       # noqa: N802
        if ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and \
                not ev.modifiers() & QtCore.Qt.ShiftModifier:
            self.submit.emit()
            return
        super().keyPressEvent(ev)

    def focusInEvent(self, ev):                        # noqa: N802
        self.focused.emit(True)
        super().focusInEvent(ev)

    def focusOutEvent(self, ev):                       # noqa: N802
        self.focused.emit(False)
        super().focusOutEvent(ev)

    def _fit(self):
        fm = self.fontMetrics()
        lines = max(1, min(6, int(self.document().size().height())))
        if not self.toPlainText() and self.placeholderText():
            # R87: an empty box shows its placeholder, which the document
            # size does not count; at a narrow width it wrapped and was
            # clipped to one line. Grow to what the placeholder needs.
            lines = max(lines, min(3, self.placeholder_lines()))
        self.setFixedHeight(lines * fm.lineSpacing() + 8)

    def placeholder_lines(self, width=None):
        """How many lines the placeholder wraps to at `width` (the text
        area's own width by default)."""
        w = int(width if width is not None else self.viewport().width())
        w -= 2 * int(self.document().documentMargin()) + 2
        if w <= 20:
            return 1
        r = self.fontMetrics().boundingRect(
            QtCore.QRect(0, 0, w, 10000),
            int(QtCore.Qt.TextWordWrap), self.placeholderText())
        return max(1, -(-r.height() // max(1, self.fontMetrics().lineSpacing())))

    def setPlaceholderText(self, text):                # noqa: N802
        super().setPlaceholderText(text)
        self._fit()

    def resizeEvent(self, ev):                         # noqa: N802
        super().resizeEvent(ev)
        self._fit()


# ----------------------------------------------------------------- panel
class AgentPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._runner = None
        self._card = None
        self._chat = None
        self._busy = False          # a turn is in flight (not: a thread exists)
        self._stopped = False       # Stop pressed; no more preview builds
        self._sid = None
        self._empty = None
        self._empty_kind = None
        self._offline = None
        self._health = None
        self._backend_state = "idle"
        self._has_messages = False  # the Welcome shows only while False
        self._last_text = ""        # the last message the user sent (R23)
        self._pending_shots = []    # "Add view" captures for the next turn
        self._shot_captions = {}    # their captions (R138 re-shows them)
        self._docs = {}             # doc Uid -> ChatState (R17)
        self._shown_key = None      # whose chat the transcript shows (R138)
        # R190: doc Uid -> the kept transcript of a document not on screen,
        # as data (Transcript entries, queued shots, last message).
        self._transcripts = {}
        self._fitting = False       # Welcome.fit in progress (R132)
        self._cur = None            # the ChatState of the turn in flight
        self._privacy_ok = False    # acknowledged this session (R02)
        self._unavailable_why = ""
        self._unavailable_kind = ""
        self._build_card = None     # the ONE build card of this turn (R76)
        self._previewed_ok = None   # sha1 a live preview built cleanly (S02)
        self._build_sig = None      # what that card last showed
        self._turn_failed = False   # this turn's build failed its checks (R75)
        self._preview_hash = None   # sha1 of the model.py last previewed (S02)
        self._pill_sig = None       # what the context line last measured (S04)
        self._brief_cache = {}      # per-object measurements between turns (S04)
        self._crane_notices = []    # R54
        self._crane_ok = None       # R56: None = not looked yet
        self._pending = None        # (PendingBuild, ctx) in flight (R93)
        self._after_build = None    # what waits on that build
        self._preview_again = False # a preview was asked for meanwhile
        self._finishing = False     # the agent is done; final build pending
        self._fix_turn = False      # this turn was sent by _send_fix
        self._last_preview_ok = None    # Result of this turn's good preview
        self._preview_intent = None     # ... short of intent.json only (S49)
        self._preview_intent_hash = None    # the script that preview built
        self._turn_budget = None    # --max-budget-usd of the turn (R101)
        self.stats = {"previews": 0, "previews_skipped": 0,
                      "previews_failed": 0, "pill_updates": 0}
        self.setMinimumWidth(320)
        self._build()
        self.restyle()
        self._probe_backend()
        # The context line MEASURES the document; poll it rather than trust a
        # signal we might miss (documents open from menus, macros, the RPC).
        self._doc_timer = QtCore.QTimer(self)
        self._doc_timer.timeout.connect(self.refresh_doc_pill)
        self._doc_timer.start(800)
        # R93: a sandboxed build runs in its own process group; quitting
        # while one is in flight must not leave it running to its timeout.
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._cancel_build)

    # ------------------------------------------------------- PUBLIC HOOKS
    def show_notice(self, title, body, actions=None, detail=None):
        """Render a designed Notice in the transcript. Returns the Notice.
        This is the ONLY sanctioned way to put system text on screen.
        `detail` (raw text) is collapsed behind a Details button."""
        self._clear_empty()
        self._has_messages = True
        n = self._add(Notice(title, body, actions=actions, detail=detail))
        if title in CRANE_NOTICE_TITLES:
            self._crane_notices.append(n)
            self._pill_sig = None       # re-check on the next poll (R54)
        return n

    def set_backend_state(self, state):
        """state in {'offline','idle','working'} -> status dot + label."""
        if state not in BACKEND_STATES:
            state = "idle"
        self._backend_state = state
        label, tok = BACKEND_STATES[state]
        self.state_text.setText(label)
        self.state_dot.set_color(style.tokens()[tok])

    def add_shot(self, path, caption):
        """Inline viewport capture. Signature unchanged - PARITY calls this.

        The capture is also queued for the next Claude turn (R25): the
        transcript must not imply the agent saw a picture it never got."""
        self._follow_active_doc()           # R138
        self._clear_empty()
        if not self._busy:
            self._shown_key = self._doc_key(self._active_document())
        self._has_messages = True
        if path and os.path.isfile(path) and path not in self._pending_shots:
            self._pending_shots.append(path)
            self._shot_captions[path] = caption
        return self._add(Shot(path, caption))

    def capture_path(self):
        """Where "Add view" writes its PNG: the active document's chat
        workspace, so the agent can read it (R25) and it is cleared with
        the chat instead of piling up in /tmp. Unique: several views in
        one second (vision.ask_in_chat) must not overwrite each other."""
        state = self._state_for(self._active_document())
        base = os.path.join(state.ws, time.strftime("view-%Y%m%d-%H%M%S"))
        path, n = base + ".png", 1
        while os.path.exists(path):
            n += 1
            path = "%s-%d.png" % (base, n)
        return path

    def workspaces(self):
        """Every chat workspace this panel is using (kept by Clear)."""
        return [st.ws for st in self._docs.values()]

    def restyle(self):
        """Re-read the mode and repaint. Called by the shell on theme flips."""
        self.setStyleSheet(style.qss(PANEL_QSS))
        t = style.tokens()
        self.send.setIcon(style.icon("arrow-up", t["btn_text"], 16, 2.4))
        for b, name in ((self.btn_measure, "ruler"), (self.btn_view, "camera"),
                        (self.btn_settings, "settings"),
                        (self.btn_new, "chat")):
            b.setIcon(style.icon(name, t["muted"], 14))
        # R53: marks rendered in the previous mode are repainted.
        for mark in self.findChildren(QtWidgets.QLabel, "LogoMark"):
            pm = style.logo_pixmap(int(mark.property("logo_h") or 14))
            if pm is not None:
                mark.setPixmap(pm)
        self.set_backend_state(self._backend_state)
        # R186: a note holding both voices carries the muted colour inline.
        for card in self.findChildren(ToolCard):
            if card.caveat_text and card.info_text:
                card.set_notes(card.caveat_text, card.info_text)
            # R205: failed rows carry the failure colour inline.
            if card.body.has_failed_rows():
                card.body.render()

    # ------------------------------------------------------------- build
    def _build(self):
        self.setObjectName("AgentPanel")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # context line: which document, and is the agent there
        ctx = QtWidgets.QWidget()
        ctx.setObjectName("Context")
        cl = QtWidgets.QHBoxLayout(ctx)
        cl.setContentsMargins(PAD, 6, PAD, 6)
        cl.setSpacing(8)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(1)
        self.doc_name = QtWidgets.QLabel("No document")
        self.doc_name.setObjectName("DocName")
        self.doc_meta = QtWidgets.QLabel("")
        self.doc_meta.setObjectName("DocMeta")
        col.addWidget(self.doc_name)
        col.addWidget(self.doc_meta)
        cl.addLayout(col, 1)
        self.state_dot = Dot()
        self.state_text = QtWidgets.QLabel("")
        self.state_text.setObjectName("StateText")
        cl.addWidget(self.state_dot, 0, QtCore.Qt.AlignVCenter)
        cl.addWidget(self.state_text, 0, QtCore.Qt.AlignVCenter)
        # R70: start a clean conversation without restarting Studio.
        self.btn_new = self._ghost("New chat", self.new_chat,
                                   "Start a new conversation. What is "
                                   "already built stays in the document.")
        cl.addWidget(self.btn_new, 0, QtCore.Qt.AlignVCenter)
        outer.addWidget(ctx)

        # R113: the way back to the script review after "Not now" (or once
        # the notice has scrolled away or a new chat cleared it). Its own
        # slim row under the context line: beside "New chat" it squeezed
        # both buttons in the 300 px sidebar of a 900x600 window (measured
        # 63 px for an 88 px button). Shown only while the active
        # document's script is still untrusted.
        self.review_bar = QtWidgets.QWidget()
        self.review_bar.setObjectName("Context")
        rl = QtWidgets.QHBoxLayout(self.review_bar)
        rl.setContentsMargins(PAD, 0, PAD, 6)
        rl.setSpacing(8)
        why = QtWidgets.QLabel("Design script not loaded")
        why.setObjectName("DocMeta")
        why.setMinimumWidth(10)
        rl.addWidget(why, 1, QtCore.Qt.AlignVCenter)
        self.btn_review = self._ghost("Review script", self._on_review_btn,
                                      "Read the design script this file "
                                      "carries before the chat uses it.")
        rl.addWidget(self.btn_review, 0, QtCore.Qt.AlignVCenter)
        self.review_bar.hide()
        outer.addWidget(self.review_bar)

        # transcript
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("Stream")
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        inner = QtWidgets.QWidget()
        inner.setObjectName("StreamInner")
        self.stream = QtWidgets.QVBoxLayout(inner)
        self.stream.setContentsMargins(PAD, 8, PAD, 16)
        self.stream.setSpacing(14)
        self.stream.addStretch(1)
        self.scroll.setWidget(inner)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._on_range)
        # R132: the Welcome is fitted to the space above the composer, so
        # it follows every resize of that space (window, composer growth).
        self.scroll.viewport().installEventFilter(self)
        outer.addWidget(self.scroll, 1)

        # composer
        wrap = QtWidgets.QWidget()
        wrap.setObjectName("ComposerWrap")
        wl = QtWidgets.QVBoxLayout(wrap)
        wl.setContentsMargins(12, 6, 12, 12)
        wl.setSpacing(6)

        self.hint = QtWidgets.QLabel("")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        self.hint.hide()
        wl.addWidget(self.hint)

        self.composer = QtWidgets.QFrame()
        self.composer.setObjectName("Composer")
        kl = QtWidgets.QVBoxLayout(self.composer)
        kl.setContentsMargins(14, 10, 8, 8)
        kl.setSpacing(4)
        self.input = PromptEdit()
        self.input.setPlaceholderText("Ask about the model, or describe a change…")
        self.input.submit.connect(self._on_send)
        self.input.textChanged.connect(self._sync_send)
        self.input.textChanged.connect(self._claim_draft)      # R210
        self.input.focused.connect(self._on_focus)
        kl.addWidget(self.input)

        tools = QtWidgets.QHBoxLayout()
        tools.setSpacing(2)
        self.btn_measure = self._ghost("Measure", self._on_build,
                                       "Measure every solid in the document")
        self.btn_view = self._ghost("Add view", self._on_capture,
                                    "Capture the 3D view into the chat")
        self.btn_settings = self._ghost("", self._on_settings,
                                        "Agent settings: backend and model")
        tools.addWidget(self.btn_measure)
        tools.addWidget(self.btn_view)
        tools.addStretch(1)
        tools.addWidget(self.btn_settings)
        self.send = QtWidgets.QPushButton()
        self.send.setObjectName("SendBtn")
        self.send.setFixedSize(30, 30)
        self.send.setIconSize(QtCore.QSize(16, 16))
        self.send.setCursor(QtCore.Qt.PointingHandCursor)
        self.send.setToolTip("Send (Enter)")
        self.send.clicked.connect(self._on_send_or_stop)
        tools.addSpacing(4)
        tools.addWidget(self.send)
        kl.addLayout(tools)
        wl.addWidget(self.composer)
        outer.addWidget(wrap)
        self._sync_send()
        self.refresh_doc_pill()

    def _ghost(self, text, fn, tip):
        b = QtWidgets.QPushButton(text)
        b.setObjectName("GhostBtn")
        b.setCursor(QtCore.Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setIconSize(QtCore.QSize(14, 14))
        b.clicked.connect(fn)
        return b

    def _on_focus(self, on):
        self.composer.setProperty("focus", bool(on))
        _repolish(self.composer)

    def _sync_send(self):
        busy = bool(self._busy)
        self.send.setEnabled(busy or bool(self.input.toPlainText().strip()))

    # ------------------------------------------------------- empty states
    def _base_url(self):
        return cfgmod.load().get("backend_url", "http://127.0.0.1:4096")

    def _probe_backend(self):
        """Ask the backend whether it is there, before the user invests a
        typed question in finding out. Off the GUI thread."""
        if engine.current() == engine.CLAUDE:
            # Finding the binary may need the login shell, and "is it signed
            # in" needs `claude auth status`: both start processes (R21/R22).
            self.set_backend_state("checking")
            probe = _keep_alive(ClaudeProbe())
            probe.done.connect(self._on_claude_probe)
            self._health = probe
            probe.start()
            return
        self._health = _keep_alive(HealthWorker(self._base_url()))
        self._health.done.connect(self._on_health)
        self._health.start()

    def _on_claude_probe(self, ok, kind, why):
        self._unavailable_kind = kind
        self._unavailable_why = why
        self._on_health(ok)

    def _on_health(self, ok):
        if not self._busy:
            self.set_backend_state("idle" if ok else "offline")
        self._connected = ok
        self._show_empty_state(ok)
        owner = getattr(self._health, "owner", None)
        if ok:
            self._note_foreign_backend(owner)
        elif getattr(self._health, "refused", None) and owner:
            self._note_refused_backend(owner)

    def _note_refused_backend(self, owner):
        """R105: say why an answering backend is not used, once per pid."""
        from . import backend
        kind, info = owner
        key = ("refused", kind, (info or {}).get("pid"))
        if getattr(self, "_foreign_noted", None) == key:
            return
        self._foreign_noted = key
        where = _hostport(self._base_url())
        if kind == backend.OTHER_USER:
            why = ("%s is served by another account on this computer. Atech "
                   "Atelier will not send your work to it." % where)
        else:
            why = ("%s is served by %s, which Atech Atelier did not start, "
                   "and ATECH_AGENT_ADOPT=0 says not to use it."
                   % (where, backend.describe(info)))
        _log("agent backend not used: %s" % why)
        self.show_notice(backend.NOTICE_TITLE,
                         why + "\n\nStop it, or change the backend address "
                         "in Settings.")

    def _note_foreign_backend(self, owner):
        """R105: a backend this Studio did not start is used, but never
        silently. Once per listener (pid), not on every probe."""
        if not owner:
            return
        from . import backend
        kind, info = owner
        if kind == backend.OWN:
            return
        key = (kind, (info or {}).get("pid"))
        if getattr(self, "_foreign_noted", None) == key:
            return
        self._foreign_noted = key
        base = self._base_url()
        _log("agent backend at %s is not this Atelier's: %s (%s)"
             % (base, backend.describe(info), kind))
        self.show_notice(backend.FOREIGN_TITLE,
                         backend.foreign_body(_hostport(base), info, kind))

    def _show_empty_state(self, connected):
        """The Welcome only while the transcript has no messages (R23); the
        offline notice whenever the engine cannot run."""
        if self._offline is not None:
            self._offline.hide()
            self._offline.deleteLater()
            self._offline = None
        if not self._has_messages:
            kind = self._welcome_kind(self._active_document())
            if self._empty is None or self._empty_kind != kind:
                self._clear_empty()
                self._empty_kind = kind
                # R132: the Welcome opens at its heading. _add follows the
                # bottom, which left "What are we building?" scrolled out
                # of sight after a document was closed.
                self._empty = self._add(self._welcome(kind), top=True)
                self._fit_welcome()
        if not connected:
            self._offline = self._offline_notice()
            self._fit_welcome()

    # ----------------------------------------------- welcome fit (R132)
    def eventFilter(self, obj, ev):                    # noqa: N802
        try:
            vp = self.scroll.viewport()
        except (AttributeError, RuntimeError):
            return False
        if obj is vp and ev.type() == QtCore.QEvent.Resize:
            self._fit_welcome()
        return False

    def _welcome_room(self):
        """(height, width) the Welcome may use: the transcript viewport,
        less the stream's margins and whatever else is in the stream (an
        offline notice)."""
        vp = self.scroll.viewport()
        m = self.stream.contentsMargins()
        width = vp.width() - m.left() - m.right()
        avail = vp.height() - m.top() - m.bottom()
        for i in range(self.stream.count()):
            w = self.stream.itemAt(i).widget()
            if w is None or w is self._empty or w.isHidden():
                continue
            h = w.heightForWidth(width) if w.hasHeightForWidth() else -1
            avail -= (h if h > 0 else w.sizeHint().height()) + \
                self.stream.spacing()
        return avail, width

    def _fit_welcome(self):
        w = self._empty
        if w is None or self._fitting or not isinstance(w, Welcome):
            return
        avail, width = self._welcome_room()
        if width < 40 or avail < 40:
            return                  # not laid out yet; the resize comes
        self._fitting = True
        try:
            # R143: with an offline / sign-in notice below it the examples
            # cannot be sent anyway; they go before the notice is pushed
            # out of sight.
            w.fit(avail, width, keep=0 if self._offline is not None else 1)
        finally:
            self._fitting = False

    def _crane_available(self):
        """R56: offer the sample crane only when its files are installed.
        Asked once (a directory glob); cached for the panel's life."""
        if self._crane_ok is None:
            try:
                from . import viewport
                self._crane_ok = bool(viewport.crane_parts())
            except Exception as exc:                   # noqa: BLE001
                _log("crane_parts: %r" % (exc,))
                self._crane_ok = False
        return self._crane_ok

    def _nodoc_actions(self):
        acts = [("New", self._on_new_document),
                ("Open file…", self._on_open_file)]
        if self._crane_available():
            # R89: the same name as the start card (shell.py).
            acts.insert(0, ("Sample crane", self._on_reference))
        return acts

    @staticmethod
    def _atech_parts(doc):
        """(has a board, [(module name, first port)]) measured off the
        document's Atech properties (R133). Never raises."""
        board, mods = False, []
        try:
            for o in getattr(doc, "Objects", None) or ():
                role = getattr(o, "AtechRole", None)
                if role == "board":
                    board = True
                elif role == "module":
                    ports = sorted(int(n) for n in
                                   (getattr(o, "AtechPorts", ()) or ()))
                    name = str(getattr(o, "AtechModule", "") or
                               getattr(o, "Label", "") or "module")
                    mods.append((name, ports[0] if ports else 99))
        except Exception as exc:                       # noqa: BLE001
            _log("welcome: %r" % (exc,))
        return board, sorted(mods, key=lambda m: m[1])

    def _welcome_kind(self, doc):
        """"nodoc", "empty", "doc", "board", or ("modules", names): which
        examples fit the active document (R133). Compared by value, so
        seating a module swaps the Welcome while the transcript is still
        empty. R146: a document with no objects gets part examples, not
        "make the walls thicker" about walls that are not there."""
        if doc is None:
            return "nodoc"
        try:
            empty = not any(_is_model_object(o)
                            for o in (getattr(doc, "Objects", None) or ()))
        except Exception:                              # noqa: BLE001
            empty = False
        if empty:
            return "empty"
        if self._is_crane(doc):
            return "crane"      # R187
        board, mods = self._atech_parts(doc)
        if mods:
            names = []
            for name, _port in mods:
                if name not in names:
                    names.append(name)
            return ("modules", tuple(names))
        return "board" if board else "doc"

    #: R187: the name viewport.open_reference_model gives the sample crane
    #: (FreeCAD appends 001, 002 ... to a second copy).
    CRANE_DOC = "SampleCrane"

    def _crane_names(self):
        """The object names the sample crane loads as (its .brep basenames,
        viewport.crane_parts), cached for the panel's life; () when the
        crane is not installed."""
        names = getattr(self, "_crane_name_set", None)
        if names is None:
            names = ()
            try:
                from . import viewport
                names = frozenset(os.path.splitext(os.path.basename(f))[0]
                                  for f in viewport.crane_parts())
            except Exception as exc:                   # noqa: BLE001
                _log("crane names: %r" % (exc,))
            self._crane_name_set = names
        return names

    def _is_crane(self, doc):
        """R187: is `doc` the sample crane? Its document name, or - once
        saved under another name - most of its objects carrying the crane's
        part names. Never raises."""
        try:
            if str(getattr(doc, "Name", "")).startswith(self.CRANE_DOC):
                return True
            names = self._crane_names()
            if not names:
                return False
            objs = [str(getattr(o, "Name", "")) for o in
                    getattr(doc, "Objects", None) or ()
                    if _is_model_object(o)]
            hits = sum(1 for n in objs if n in names)
            return bool(objs) and hits >= 3 and hits * 2 >= len(objs)
        except Exception as exc:                       # noqa: BLE001
            _log("is crane: %r" % (exc,))
            return False

    #: R187 (GUI r8_23): examples about the crane that is on screen - an
    #: assembly of bought and printed parts with a slewing turret, a jib,
    #: a leadscrew hoist and gear pairs - not "make the walls thicker".
    #: Each one can be answered by measuring the open document.
    CRANE_PROMPTS = (
        "What is the volume and mass of every part of the crane?",
        "How tall is the crane, and how far does the jib reach from the "
        "mast?",
        "Which parts of the crane touch or overlap each other?",
    )

    @staticmethod
    def _and(items):
        items = list(items)
        if len(items) < 2:
            return "".join(items)
        return "%s and %s" % (", ".join(items[:-1]), items[-1])

    def _welcome(self, kind):
        # Plain words, no project jargon (R26): this is the first thing a
        # new user reads.
        if isinstance(kind, tuple) and kind and kind[0] == "modules":
            # R133: an Atech board with seated modules. The examples name
            # the modules that are actually there.
            names = list(kind[1]) or ["module"]
            # More than three names make a card that fills the panel.
            the = self._and("the %s" % n for n in names) \
                if len(names) <= 3 else "the modules"
            w = Welcome(
                "Build around this board",
                "Ask about the board and its modules, or describe a case "
                "for them. Every size in a reply is measured off the "
                "model.",
                prompts=[
                    "Design a case around the board with an opening "
                    "over %s" % the,
                    "Which modules are seated, and on which ports?",
                    "Add a button module on a free port",
                ])
        elif kind == "crane":
            # R187: the sample crane gets examples about the crane.
            w = Welcome(
                "Ask about the sample crane",
                "A measured crane assembly. Ask about its parts, or describe "
                "a change. Every number in a reply is measured off the "
                "solids.",
                prompts=list(self.CRANE_PROMPTS))
        elif kind == "board":
            w = Welcome(
                "Build around this board",
                "Seat modules on the board, or describe a case for it. "
                "Every size in a reply is measured off the model.",
                prompts=[
                    "Add a button and a light module to the board",
                    "Design a case that fits around the board",
                    "Which ports can take a speaker module?",
                ])
        elif kind == "empty":
            # R146: nothing to measure or thicken yet - what to build.
            w = Welcome(
                "What are we building?",
                "This document is empty. Describe a part and the agent "
                "builds it here as a real solid. Every size it reports is "
                "measured from the model.",
                prompts=[
                    "Make a 60 x 40 x 20 mm box with 2 mm walls",
                    "A phone stand that holds a phone at 60 degrees",
                    "A round knob, 30 mm across, for a 6 mm D-shaft",
                ])
        elif kind == "nodoc":
            w = Welcome(
                "What are we building?",
                "Describe a part and the agent builds it as a real solid in "
                "a new document. Every size it reports is measured from the "
                "model.",
                prompts=[
                    "Make a 60 x 40 x 20 mm box with 2 mm walls",
                    "A phone stand that holds a phone at 60 degrees",
                    "A round knob, 30 mm across, for a 6 mm D-shaft",
                ],
                actions=self._nodoc_actions())
        else:
            w = Welcome(
                "Ask about this model",
                "Describe a change, or ask a question. Every number in a "
                "reply is measured off the solid.",
                prompts=[
                    "What is the volume and mass of every solid here?",
                    "Make the walls 1 mm thicker",
                    "Add four 3 mm mounting holes, 5 mm from the corners",
                ])
        # R73: both branches - the no-document examples used to return
        # before this line and did nothing when clicked.
        w.picked.connect(self._use_prompt)
        return w

    def _offline_notice(self):
        if engine.current() == engine.CLAUDE:
            if self._unavailable_kind == "auth":
                return self._add(self._auth_notice(
                    self._probe_backend_again))
            from . import claude_cli
            return self._add(Notice(
                "Claude Code not found",
                "The chat runs on Claude Code, installed on this computer. "
                "Install it by running this in a terminal:\n\n"
                "    %s\n\n"
                "then sign in by running `%s`, and press Retry. "
                "Instructions: %s\n"
                "Already installed somewhere else? Set its path in "
                "Settings." % (claude_cli.INSTALL_COMMAND,
                               claude_cli.LOGIN_COMMAND,
                               claude_cli.INSTALL_URL),
                actions=[("Retry", self._probe_backend_again),
                         ("Settings…", self._on_settings)],
                detail=self._unavailable_why or None))
        base = self._base_url()
        return self._add(Notice(
            "Agent backend not reachable",
            "Atech Atelier talks to a local agent process on %s. Nothing is "
            "listening there right now. Start it with "
            "opencode serve --port 4096." % _hostport(base),
            actions=[("Retry", self._probe_backend_again),
                     ("Change address…", self._on_settings)]))

    def _auth_notice(self, retry):
        from . import claude_cli
        return Notice(
            "Sign in to Claude Code",
            "Claude Code is not signed in. In a terminal, run\n"
            "    %s\n"
            "follow its steps, then press Retry. (Older Claude Code: run "
            "`claude` and type /login.)"
            % claude_cli.LOGIN_COMMAND,
            actions=[("Open terminal", self._open_claude_terminal),
                     ("Retry", retry)])

    def _use_prompt(self, text):
        self.input.setPlainText(text)
        self.input.setFocus()
        self.input.moveCursor(QtGui.QTextCursor.End)

    def _clear_empty(self):
        for attr in ("_empty", "_offline"):
            w = getattr(self, attr, None)
            if w is not None:
                w.hide()
                w.deleteLater()
                setattr(self, attr, None)
        self._empty_kind = None

    def _probe_backend_again(self):
        """Retry on an offline notice: re-check the engine. Never adds a
        second Welcome once there are messages (R23)."""
        if self._offline is not None:
            self._offline.hide()
            self._offline.deleteLater()
            self._offline = None
        if not self._busy:
            self.set_backend_state("idle")
        self._probe_backend()

    # Kept for callers outside this file (backend.py).
    _on_retry = _probe_backend_again

    def _open_claude_terminal(self):
        """Run `claude` in a terminal so the user can sign in (R21).

        A desktop terminal first (Claude Code's sign-in is a full-screen
        terminal app); the in-app terminal dock if none can be started."""
        from . import claude_cli
        exe = claude_cli.find_claude() or "claude"
        env = QtCore.QProcessEnvironment()
        for k, v in claude_cli._child_env().items():
            env.insert(k, v)
        for term, args in (("x-terminal-emulator", ["-e", exe]),
                           ("gnome-terminal", ["--", exe]),
                           ("konsole", ["-e", exe]),
                           ("xfce4-terminal", ["-x", exe]),
                           ("kitty", [exe]),
                           ("alacritty", ["-e", exe]),
                           ("xterm", ["-e", exe])):
            path = shutil.which(term)
            if not path:
                continue
            proc = QtCore.QProcess()
            proc.setProgram(path)
            proc.setArguments(args)
            proc.setProcessEnvironment(env)
            proc.setWorkingDirectory(os.path.expanduser("~"))
            ok = proc.startDetached()   # MEASURED PySide6 6.8.3: a bool
            if isinstance(ok, tuple):
                ok = ok[0]
            if ok:
                _log("opened %s running %s" % (term, exe))
                return
        try:
            from . import terminal_dock
            dock = terminal_dock.ensure_terminal()
            term = getattr(dock.widget(), "term", None) if dock else None
            if term is not None and term.write("%s\n" % exe):
                return
        except Exception as exc:                       # noqa: BLE001
            _log("terminal dock: %r" % (exc,))
        self._flash_hint("Could not open a terminal. Open one yourself and "
                         "run: claude")

    def _active_document(self):
        try:
            import FreeCAD
            return FreeCAD.ActiveDocument
        except Exception:                              # noqa: BLE001
            return None

    def _doc_signature(self, doc):
        """Cheap: which document, its label, how many objects, and which
        documents are open. No per-object work (S04)."""
        try:
            import FreeCAD
            docs = tuple(sorted(FreeCAD.listDocuments()))
        except Exception:                              # noqa: BLE001
            docs = ()
        if doc is None:
            return (None, docs)
        try:
            n = len(doc.Objects)
        except Exception:                              # noqa: BLE001
            n = -1
        return (id(doc), getattr(doc, "Name", ""), getattr(doc, "Label", ""),
                n, docs)

    def refresh_doc_pill(self, force=False):
        """The context line MEASURES the document; it never asserts one.

        Polled every 800 ms, but it only re-counts when the active document,
        its label, its object count or the open documents changed (S04)."""
        doc = self._active_document()
        # R144: a closed or switched-away document's transcript does not
        # stay on screen under the new header. Cheap (a key compare) so it
        # runs on every poll: a document closed mid-turn is followed as soon
        # as the turn ends, although the signature no longer changes then.
        followed = self._follow_active_doc(draft=True)
        sig = self._doc_signature(doc)
        if not force and not followed and sig == self._pill_sig:
            return
        self._pill_sig = sig
        self.stats["pill_updates"] += 1
        if doc is None:
            self.doc_name.setText("No document")
            self.doc_meta.setText("Nothing open")
        else:
            name = getattr(doc, "Label", None) or getattr(doc, "Name", "document")
            self.doc_name.setText(str(name))
            try:
                n = sum(1 for o in doc.Objects if _is_model_object(o))
            except Exception:                          # noqa: BLE001
                n = None
            self.doc_meta.setText(
                _plural(n, "object") if n is not None else "objects: —")
        self._drop_stale_crane_notices(sig[-1])
        self._check_untrusted(doc)      # R98
        self._sync_review_btn(doc)      # R113
        # The welcome follows the document: swap it when one opens or closes,
        # but only while the transcript is still empty.
        if (followed and not self._has_messages) or (
                self._empty is not None and
                self._empty_kind != self._welcome_kind(doc)):
            self._show_empty_state(getattr(self, "_connected", True))

    def _drop_stale_crane_notices(self, open_docs):
        """R54: a "sample crane not available" notice goes once a crane
        document is open after all."""
        if not self._crane_notices:
            return
        if not any(str(n).startswith("SampleCrane") for n in open_docs):
            return
        for n in self._crane_notices:
            try:
                n.hide()
                n.deleteLater()
            except RuntimeError:                       # already deleted
                pass
        self._crane_notices = []

    def _on_reference(self):
        try:
            from . import viewport
            viewport.open_reference_model()
        except Exception as exc:                       # noqa: BLE001
            _log("reference model failed: %r" % (exc,))
            self.show_notice("Could not open the sample crane",
                             "The details are in the Report view.")
        self.refresh_doc_pill()

    def _on_new_document(self):
        try:
            import FreeCAD
            FreeCAD.newDocument()
        except Exception as exc:                       # noqa: BLE001
            _log("newDocument failed: %r" % (exc,))
            self.show_notice(
                "Could not create a document",
                "FreeCAD refused to open a new document. The details are in "
                "the Report view.")
            return
        self.refresh_doc_pill()

    def _on_open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open a file", os.path.expanduser("~"),
            "CAD files (*.FCStd *.step *.stp *.iges *.igs *.brep);;All files (*)")
        if not path:
            return
        try:
            import FreeCAD
            FreeCAD.openDocument(path)
        except Exception as exc:                       # noqa: BLE001
            _log("openDocument failed: %r" % (exc,))
            self.show_notice(
                "Could not open that file",
                "%s could not be read as a CAD document. The details are in "
                "the Report view." % os.path.basename(path))
            return
        self.refresh_doc_pill()

    def _on_capture(self):
        # R158: "Add view" looks from where "Ask about this view" looks
        # (vision.views_for, R145): an Atech board's module face, not the
        # isometric corner that showed the back of the board.
        from . import capture, vision
        try:
            name = vision.views_for(self._active_document())[0]
        except Exception as exc:                       # noqa: BLE001
            _log("add view: %r" % (exc,))
            name = "Isometric"
        capture.capture_to_panel(self, view_name=name)

    def add_note(self, text):
        """capture.py's failure hook: a plain reason, never a broken image."""
        self.show_notice("Could not capture the view", text)

    # ---------------------------------------------------------- transcript
    def _add(self, widget, top=False):
        self.stream.insertWidget(self.stream.count() - 1, widget)
        # R143: under a Welcome (nothing typed yet) the view stays at the
        # heading, also when an offline / sign-in notice is added below it.
        if top or (self._empty is not None and not self._has_messages):
            # R132: the Welcome is read from its heading down.
            self._follow = False
            QtCore.QTimer.singleShot(0, self._scroll_top)
            QtCore.QTimer.singleShot(60, self._scroll_top)
            return widget
        # Scroll once the layout has actually grown: a zero-delay scroll runs
        # before the new widget has a height, and lands short of it.
        self._follow = True
        QtCore.QTimer.singleShot(0, self._scroll_bottom)
        QtCore.QTimer.singleShot(60, self._scroll_bottom)
        return widget

    def _scroll_top(self):
        # R143: the first-run view (no document, sign-in notice) is read
        # from "What are we building?" down. R132 used to keep the bottom
        # whenever an offline/sign-in notice was there, which is exactly the
        # first-run view: heading and pills scrolled away. The Welcome now
        # gives up its examples for the notice instead (_fit_welcome), so
        # its Retry stays in reach from the top.
        if self._empty is not None and not self._has_messages:
            self.scroll.verticalScrollBar().setValue(0)

    def _on_range(self, _lo, hi):
        if getattr(self, "_follow", False):
            self.scroll.verticalScrollBar().setValue(hi)

    def _scroll_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        QtCore.QTimer.singleShot(300, self._stop_follow)

    def _stop_follow(self):
        self._follow = False

    def say(self, text, role="agent"):
        """Transcript only. System text goes through show_notice()."""
        self._clear_empty()
        self._has_messages = True
        return self._add(Bubble(text, role))

    def _flash_hint(self, text):
        self.hint.setText(text)
        self.hint.show()
        QtCore.QTimer.singleShot(4000, self.hint.hide)

    # ------------------------------------------------------------- actions
    def _on_send_or_stop(self):
        if self._busy:
            self._on_stop()
        else:
            self._on_send()

    def _on_stop(self):
        """Stop the turn: the process is signalled, and nothing more is
        built from it - not even a live preview already queued (R19)."""
        self._stopped = True
        self._stop_elapsed()
        timer = getattr(self, "_watch_timer", None)
        if timer is not None:
            timer.stop()
        self._cancel_build()
        if self._chat is not None:
            try:
                if self._chat.isRunning():
                    self._chat.requestInterruption()
                    cancel = getattr(self._chat, "cancel", None)
                    if callable(cancel):
                        cancel()
            except RuntimeError:                       # wrapper gone
                pass
        if self._card:
            self._card.set_status("stopped", "idle")
            self._card = None
        self._busy = False
        self._finishing = False
        self._set_sending(False)
        self.set_backend_state("idle")
        self._restore_input()

    def _set_sending(self, sending):
        t = style.tokens()
        self.send.setIcon(style.icon("stop" if sending else "arrow-up",
                                     t["btn_text"], 16, 2.4))
        self.send.setToolTip("Stop" if sending else "Send (Enter)")
        self._sync_send()

    def _restore_input(self):
        """Put the last message back in the box, unless the user has already
        typed something new there (R23)."""
        if self._last_text and not self.input.toPlainText().strip():
            self.input.setPlainText(self._last_text)
            self.input.moveCursor(QtGui.QTextCursor.End)

    def _on_send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        if self._busy:
            # Non-destructive: the user's text stays in the input.
            self._flash_hint(
                "Still working on the previous message. Press stop to interrupt.")
            return

        if engine.current() == engine.CLAUDE:
            if not self._privacy_gate():
                return              # the notice is up; the text stays put
            self._follow_active_doc()       # R138
            self._last_text = text
            self.input.clear()
            self.say(text, role="user")
            self._attempt = 0
            if not self._send_claude(text):
                self._restore_input()
            return

        cfg = cfgmod.load()
        base = cfg.get("backend_url", "http://127.0.0.1:4096")

        try:
            if not self._sid:
                self._sid = client.Backend(base).new_session()
        except Exception as exc:                       # noqa: BLE001
            _log("new_session failed: %r" % (exc,))
            self._clear_empty()
            self.set_backend_state("offline")
            self.show_notice(
                "Agent backend not reachable",
                "Atech Atelier talks to a local agent process on %s. Nothing "
                "is listening there right now. Start it with "
                "opencode serve --port 4096." % _hostport(base),
                actions=[("Retry", self._probe_backend_again),
                         ("Change address…", self._on_settings)])
            return

        # All guards passed - only now is it safe to destroy the user's text.
        self._last_text = text
        self.input.clear()
        self.say(text, role="user")
        self._card = ToolCard("Thinking", cfg.get("model") or "default model",
                              mono=False)
        self._add(self._card)

        self._set_busy(True)
        chat = client.ChatWorker(
            base, self._sid, text,
            cfg.get("provider") or None, cfg.get("model") or None, parent=None)
        _keep_alive(chat)
        chat.chunk.connect(self._only(chat, self._on_chunk))
        chat.tool.connect(self._only(chat, self._on_tool))
        chat.finished_ok.connect(self._only(chat, self._on_reply))
        chat.failed.connect(self._only(chat, self._on_chat_failed))
        self._chat = chat
        chat.start()
        self._sync_send()

    def _set_busy(self, busy):
        self._busy = bool(busy)
        if busy:
            self._stopped = False
        self._set_sending(busy)
        self.set_backend_state("working" if busy else "idle")

    def _only(self, worker, handler):
        """Deliver a worker's signal only while it is the current turn.

        A stopped run can still emit (its "cancelled", a late result) after
        the user has started the next one; that must not touch the new
        turn's card or state."""
        def slot(*args):
            if worker is self._chat:
                handler(*args)
        return slot

    # ------------------------------------------------------ data notice
    def _privacy_gate(self):
        """First send: say what leaves the machine and what is stored, once
        (R02). True when the message may go. The wording lives in
        settings.PRIVACY_NOTICE_BODY (final, owner decision 2026-10-03)."""
        if self._privacy_ok or cfgmod.privacy_acknowledged():
            self._privacy_ok = True
            return True
        if getattr(self, "_privacy_notice", None) is not None:
            return False            # already on screen
        self._privacy_notice = self.show_notice(
            cfgmod.PRIVACY_NOTICE_TITLE, cfgmod.privacy_notice_body(),
            actions=[("Continue", self._on_privacy_ok),
                     ("Not now", self._on_privacy_later)])
        return False

    def _on_privacy_ok(self):
        self._privacy_ok = True
        if not cfgmod.acknowledge_privacy():
            _log("could not persist the data-notice acknowledgement")
        self._dismiss_privacy()
        self._on_send()

    def _on_privacy_later(self):
        self._dismiss_privacy()

    def _dismiss_privacy(self):
        n = getattr(self, "_privacy_notice", None)
        self._privacy_notice = None
        if n is not None:
            for b in getattr(n, "buttons", []):
                b.setEnabled(False)

    # ------------------------------------------------ Claude Code + build
    MAX_FIX_ATTEMPTS = 2

    def _doc_key(self, doc):
        if doc is None:
            return NO_DOC
        return getattr(doc, "Uid", None) or getattr(doc, "Name", NO_DOC)

    def _state_for(self, doc):
        """The chat state of `doc`, created (and adopted) on first use.

        Adopt runs once per document, when the chat first meets it: a file
        the agent built earlier gets its script back into model.py, so the
        agent edits that design instead of duplicating it (R17).

        S07: a document whose chat was saved in an earlier Studio session
        gets that chat back (workspace, Claude session, last build) as long
        as the workspace folder still exists.

        R67: a workspace deleted under a live chat is recreated; the Claude
        session is dropped with it (a session is stored per working folder,
        so --resume from a new folder cannot find it)."""
        key = self._doc_key(doc)
        state = self._docs.get(key)
        if state is not None:
            if doc is not None:
                state.doc_name = doc.Name
            if not os.path.isdir(state.ws):
                _log("workspace %s is gone; starting a new one" % state.ws)
                state.ws = build.new_workspace()
                state.sid = None
                if doc is not None:
                    try:
                        state.prev = build.adopt(doc, state.ws) or state.prev
                    except Exception as exc:           # noqa: BLE001
                        _log("adopt: %r" % (exc,))
            return state
        state = self._restore_state(key, doc)
        if state is not None:
            self._docs[key] = state
            return state
        state = ChatState(key, getattr(doc, "Name", None),
                          build.new_workspace())
        if doc is not None:
            try:
                state.prev = build.adopt(doc, state.ws)
            except Exception as exc:                   # noqa: BLE001
                _log("adopt: %r" % (exc,))
        self._docs[key] = state
        self._offer_review(state, doc)
        return state

    # ------------------------------------------- untrusted script (R98)
    def _check_untrusted(self, doc):
        """A document that opens with an agent script Studio did not write
        here gets the review notice right away, not after the first send.
        Cheap unless the document has agent-built objects."""
        if doc is None:
            return
        state = self._docs.get(self._doc_key(doc))
        if state is not None:
            self._offer_review(state, doc)
            return
        try:
            flagged = build._flagged(doc)
            if not flagged:
                return
            store = build._load_trust()
            if all(build._is_trusted(doc, o, store) for o in flagged):
                return
        except Exception as exc:                       # noqa: BLE001
            _log("untrusted check: %r" % (exc,))
            return
        self._state_for(doc)            # adopts; offers the review

    def _offer_review(self, state, doc):
        prev = state.prev if isinstance(state.prev, dict) else {}
        if not prev.get("untrusted_script") or state.review_offered:
            return
        state.review_offered = True
        name = getattr(doc, "Label", None) or getattr(doc, "Name", "This file")
        state.review_notice = self.show_notice(
            "This file contains a design script from elsewhere",
            "%s carries a design script that Atech Atelier did not write on "
            "this computer. It was not loaded into the chat and has not run. "
            "Review it first: if you use it, the agent edits that design; "
            "otherwise the agent starts a new one beside the objects already "
            "there." % name,
            actions=[("Review script…",
                      functools.partial(self._review_script, state)),
                     ("Not now",
                      functools.partial(self._dismiss_review, state))])

    def _dismiss_review(self, state):
        n = getattr(state, "review_notice", None)
        for b in getattr(n, "buttons", []) if n is not None else ():
            try:
                b.setEnabled(False)
            except RuntimeError:                       # notice deleted
                pass
        self._sync_review_btn()

    @staticmethod
    def _needs_review(state):
        if state is None:
            return False
        if getattr(state, "untrusted", None) is not None:
            return True
        prev = state.prev if isinstance(state.prev, dict) else {}
        return bool(prev.get("untrusted_script"))

    @staticmethod
    def _untrusted_objects(state):
        carried = getattr(state, "untrusted", None)
        if carried is not None:
            return carried
        return ((state.prev if isinstance(state.prev, dict) else None)
                or {}).get("untrusted_objects") or []

    def _sync_review_btn(self, doc=None):
        """R113: "Review script" in the context line while the ACTIVE
        document's chat holds a script that is still untrusted. Never
        adopts or creates a chat state: it only reads the one there is."""
        bar = getattr(self, "review_bar", None)
        if bar is None:
            return
        if doc is None:
            doc = self._active_document()
        state = self._docs.get(self._doc_key(doc)) if doc is not None \
            else None
        bar.setVisible(self._needs_review(state))

    def _on_review_btn(self):
        doc = self._active_document()
        state = self._docs.get(self._doc_key(doc)) if doc is not None \
            else None
        if not self._needs_review(state):
            self._sync_review_btn(doc)
            return None
        return self._review_script(state)

    def _untrusted_script(self, doc):
        try:
            flagged = build._flagged(doc)
            if not flagged:
                return ""
            newest = build._newest(flagged, doc)
            return getattr(newest, "AtechAgentScript", "") or ""
        except Exception as exc:                       # noqa: BLE001
            _log("untrusted script: %r" % (exc,))
            return ""

    def _review_script(self, state):
        """Open the script read-only; "Use this script" trusts it."""
        doc = self._state_doc(state)
        if doc is None:
            self._flash_hint("That document is no longer open.")
            return None
        objs = self._untrusted_objects(state)
        dlg = ScriptReview(self._untrusted_script(doc), objs, parent=self)
        dlg.accepted.connect(functools.partial(self._trust_script, state))
        self._review_dialog = dlg
        dlg.open()                  # window-modal, never blocks the loop
        return dlg

    def _trust_script(self, state):
        doc = self._state_doc(state)
        if doc is None:
            return False
        try:
            n = build.trust_script(doc, state.ws)
            state.prev = build.adopt(doc, state.ws) or state.prev
        except Exception as exc:                       # noqa: BLE001
            _log("trust_script: %r" % (exc,))
            self.show_notice("Could not use that script",
                             "The details are in the Report view.")
            return False
        state.good_hash = None      # never built here: the next build runs it
        state.failed = None
        state.untrusted = None
        self._dismiss_review(state)
        self.show_notice(
            "Design script accepted",
            "The chat continues from it (%s): the next message edits that "
            "design." % _plural(n, "object"))
        return True

    def _restore_state(self, key, doc):
        """S07: the saved chat of this document, or None."""
        if key == NO_DOC or doc is None:
            return None
        rec = load_sessions().get(key)
        if not isinstance(rec, dict):
            return None
        ws = rec.get("ws")
        if not isinstance(ws, str) or not os.path.isdir(ws):
            return None
        state = ChatState(key, doc.Name, ws,
                          rec.get("prev") if isinstance(rec.get("prev"), dict)
                          else None)
        sid = rec.get("sid")
        state.sid = sid if isinstance(sid, str) and sid else None
        if state.prev is not None:
            # The record names the document as it was; follow a rename.
            state.prev = dict(state.prev, doc=doc.Name)
        state.framed = True             # the user already has a view of it
        state.faced = True
        _log("restored chat of %s: %s (session %s)" % (doc.Name, ws,
                                                        state.sid))
        return state

    def _remember(self, state):
        """S07: persist this chat so a restart can pick it up."""
        if state is not None and state.key != NO_DOC:
            save_session(state.key, state)

    def _state_doc(self, state):
        """The live document a state belongs to, or None if it was closed."""
        if state is None or state.key == NO_DOC:
            return None
        try:
            import FreeCAD
            for name in FreeCAD.listDocuments():
                d = FreeCAD.getDocument(name)
                if getattr(d, "Uid", None) == state.key or (
                        not getattr(d, "Uid", None) and name == state.key):
                    return d
        except Exception:                              # noqa: BLE001
            pass
        return None

    def _readonly_copy(self, src, dst):
        """Copy `src` to `dst` as a 0444 file. True on success."""
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                os.chmod(dst, 0o644)
            shutil.copyfile(src, dst)
            os.chmod(dst, 0o444)
            return True
        except OSError as exc:
            _log("reference copy failed: %r" % (exc,))
            return False

    def _reference_copy(self, ws):
        """ATECH_ASSEMBLY.md copied read-only into the workspace (R14).

        Claude runs in acceptEdits mode, so any --add-dir is a folder it may
        rewrite unasked; the repo's docs/ was one, and that file feeds every
        future system prompt. Returns (source, copy) or (None, None)."""
        src = build.assembly_doc()
        if not src:
            return None, None
        dst = os.path.join(ws, os.path.basename(src))
        if not self._readonly_copy(src, dst):
            return src, None
        return src, dst

    #: R101/D44: words that make a request an Atech one. "module" alone is
    #: not one of them (a gear module is not an Atech module).
    _ATECH_WORDS = re.compile(
        r"\batech\b|atech_ports|atech_modules|\b14[- ]?port\b|"
        r"\bport\s*\d{1,2}\b|\bports?\s+\d{1,2}\s*(?:and|,|-)\s*\d{1,2}\b|"
        r"\bmodules?\b[^.\n]{0,40}\bboard\b|\bboard\b[^.\n]{0,40}\bmodules?\b",
        re.I)

    def _involves_atech(self, text, doc, ws):
        """Does this turn involve Atech modules? The request names them, the
        document holds a seated board/module, or the chat's model.py
        imports the port library. Measured off the document and the file,
        never assumed."""
        if text and self._ATECH_WORDS.search(text):
            return True
        # R110: build.mentions_atech is what system_prompt reads; a request
        # either regex recognises ("a button module") involves Atech.
        fn = getattr(build, "mentions_atech", None)
        try:
            if text and callable(fn) and fn(text):
                return True
        except Exception:                              # noqa: BLE001
            pass
        try:
            for o in getattr(doc, "Objects", None) or ():
                if getattr(o, "AtechRole", None) or \
                        getattr(o, "AtechPorts", None):
                    return True
        except Exception:                              # noqa: BLE001
            pass
        try:
            with open(os.path.join(ws, build.SCRIPT), encoding="utf-8") as fh:
                code = fh.read()
        except (OSError, UnicodeDecodeError):
            return False
        fn = getattr(build, "_uses_atech_ports", None)
        try:
            return bool(fn(code)) if callable(fn) else "atech_ports" in code
        except Exception:                              # noqa: BLE001
            return "atech_ports" in code

    #: S17: the port library the agent may READ. In a subfolder, so the copy
    #: can never shadow the real module on an import from the workspace
    #: (atech_ports finds its meshes relative to its own __file__).
    REFERENCE_DIR = "reference"
    LIBRARY_FILES = ("atech_ports.py", "atech_modules.py")

    def _library_copy(self, ws):
        """S17: atech_ports.py, atech_modules.py (and the S21 API card when
        the library has one) copied read-only into <ws>/reference each
        turn, like ATECH_ASSEMBLY.md. Still exactly one --add-dir; the repo's
        projects/ folder is never granted. Returns the copied paths."""
        try:
            src_dir = build._projects_dir()
        except Exception:                              # noqa: BLE001
            src_dir = None
        if not src_dir:
            return []
        out = []
        ref = os.path.join(ws, self.REFERENCE_DIR)
        for name in self.LIBRARY_FILES:
            src = os.path.join(src_dir, name)
            if os.path.isfile(src) and self._readonly_copy(
                    src, os.path.join(ref, name)):
                out.append(os.path.join(ref, name))
        card = self._api_card(src_dir)
        if card:
            dst = os.path.join(ref, "ATECH_API.md")
            tmp = os.path.join(ref, ".ATECH_API.md.tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(card)
                if self._readonly_copy(tmp, dst):
                    out.append(dst)
            except OSError as exc:
                _log("api card: %r" % (exc,))
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return out

    #: R216: the agent kit modules ./check and atech_cad run on. They live
    #: in the addon (build.KIT_DIR), outside the chat's one --add-dir, so a
    #: traceback naming them sent the agent to read a folder it may not
    #: (S7 c1r77: a refused Read of agent_kit mid-turn). atech_cad.py and
    #: the examples are already copied into the workspace by build.py.
    KIT_REFERENCE = ("atech_geom.py", "check.py")

    def _kit_copy(self, ws):
        """R216: read-only copies of KIT_REFERENCE in <ws>/reference/kit,
        each turn, like the port library (S17). Still exactly one
        --add-dir. Returns the copied paths."""
        kit = getattr(build, "KIT_DIR", None)
        if not kit or not os.path.isdir(kit):
            return []
        out = []
        dst_dir = os.path.join(ws, self.REFERENCE_DIR, "kit")
        for name in self.KIT_REFERENCE:
            src = os.path.join(kit, name)
            dst = os.path.join(dst_dir, name)
            if os.path.isfile(src) and self._readonly_copy(src, dst):
                out.append(dst)
        return out

    def _api_card(self, src_dir):
        """The S21 API card (atech_ports.api_card via build._api_card,
        WS-BUILD/WS-MODULES) when the library has one; None otherwise -
        never a stand-in."""
        fn = getattr(build, "_api_card", None)
        if not callable(fn):
            return None
        try:
            card = fn()
        except Exception as exc:                       # noqa: BLE001
            _log("api_card: %r" % (exc,))
            return None
        return card if isinstance(card, str) and card.strip() else None

    def _turn_args(self, ws, text=None, doc=None):
        """(system prompt, agent_argv kwargs) for one turn. The flags come
        from claude_cli.agent_argv (S16) in the worker: the isolated launch,
        the exact ./check allowlist (S10) and exactly ONE --add-dir, the
        chat's own workspace. Nothing outside it is granted (R14, R78).

        ATECH_ASSEMBLY.md is copied only when the request or the document
        involves Atech (R101, D44): in a plain chat the agent read it anyway
        and spent the turn on a board it was never asked about. A caller
        that passes neither the request nor the document (text=None,
        doc=None: tests/eval/fc_build.py) cannot be judged, so it keeps the
        copy as before rather than silently losing it on an Atech prompt."""
        from . import claude_cli
        judged = not (text is None and doc is None)
        atech = self._involves_atech(text or "", doc, ws) if judged else True
        # R110: the request decides the prompt too, not only the copy. With
        # system_prompt(ws) alone, wants_atech() saw only the document and
        # model.py, so "seat a button module on port 2" in a fresh document
        # got the two-line pointer while ATECH_ASSEMBLY.md was copied. One
        # verdict now drives both. Unjudged callers keep system_prompt's
        # own reading (plus the request when there is one).
        sp = build.system_prompt(ws, request=text,
                                 atech=atech if judged else None)
        src, copy = self._reference_copy(ws) if atech else \
            (build.assembly_doc(), None)
        if src and copy:
            sp = sp.replace(src, copy)
        elif src and not atech:
            sp = sp.replace(src, "ATECH_ASSEMBLY.md (not provided: this "
                                 "request does not involve Atech modules)")
        elif src:
            # No copy, no pointer: the agent must not be sent to read a file
            # it has no access to.
            sp = sp.replace(src, "the Atech assembly reference (unavailable)")
        lib = self._library_copy(ws)
        kit = self._kit_copy(ws)        # R216
        if lib or kit:
            sp += ("\nREFERENCE FILES (read-only copies; import the real "
                   "modules as shown above, never from this folder):\n"
                   + "".join("    %s\n" % p for p in lib + kit))
        if kit:
            sp += ("A traceback may name the kit's installed folder (%s); "
                   "you cannot read that folder - read the copies above "
                   "instead.\n" % getattr(build, "KIT_DIR", "agent_kit"))
        agent = dict(claude_cli.agent_settings(), ws=ws,
                     allowed=claude_cli.CHECK_ALLOW)
        return sp, agent

    def _turn_images(self, ws):
        """Queued captures, copied into the workspace if they are elsewhere
        (a capture made while another document was active)."""
        out = []
        for p in self._pending_shots:
            if not os.path.isfile(p):
                continue
            if os.path.dirname(os.path.realpath(p)) != os.path.realpath(ws):
                dst = os.path.join(ws, os.path.basename(p))
                try:
                    shutil.copyfile(p, dst)
                    p = dst
                except OSError as exc:
                    _log("capture copy failed: %r" % (exc,))
                    continue
            out.append(p)
        return out

    def _brief(self, doc):
        """build.document_brief, with the per-object measurement cache when
        WS-BUILD's brief accepts one (S04)."""
        try:
            import inspect
            takes = "cache" in inspect.signature(
                build.document_brief).parameters
        except (TypeError, ValueError):
            takes = False
        if takes:
            return build.document_brief(doc, cache=self._brief_cache)
        return build.document_brief(doc)

    def _send_claude(self, text, state=None, fix=False):
        """One Claude Code turn. The agent writes model.py into the chat
        workspace of the document active NOW (or `state`, for a fix turn);
        when the turn ends Studio builds it (see build.py).

        Returns True when the turn started. On any setup failure the user
        gets a notice (never a silent loss) and False (R19, R67)."""
        from . import claude_cli
        try:
            doc = self._active_document() if state is None else None
            if state is None:
                state = self._state_for(doc)
                brief_doc = doc
                if getattr(state, "adopt_on_first_turn", False):
                    state.adopt_on_first_turn = False
                    self._continue_design(state, doc)       # R200
            else:
                if not os.path.isdir(state.ws):     # R67, on a fix turn
                    os.makedirs(state.ws)
                brief_doc = self._state_doc(state)
            self._cur = state
            self._shown_key = state.key     # R138
            self._before = build.snapshot(state.ws)
            # Live preview: build model.py the moment the agent writes it,
            # not when the whole turn ends. _applied is the snapshot of what
            # was last built, so the end of the turn only rebuilds what
            # changed since.
            self._applied = dict(self._before)
            self._preview_error = ""
            self._preview_intent = None     # S49
            # S02: the script on disk counts as built only when it is the
            # last one that built cleanly - a fix turn starts from a script
            # that FAILED, and an identical rewrite of it must still be
            # built (and its failure reported), not skipped.
            h0 = self._script_hash(state.ws)
            self._preview_hash = h0 if h0 is not None and \
                h0 == getattr(state, "good_hash", None) else None
            self._previewed_ok = None
            # A live preview of an EARLIER turn is that turn's result now:
            # this turn's first preview must add its own undo step, not
            # undo and replace the previous turn's (build._merge_preview).
            if isinstance(state.prev, dict) and state.prev.get("preview"):
                state.prev = {k: v for k, v in state.prev.items()
                              if k not in ("preview", "undo_count")}
            self._watch_workspace()
            prompt = "%s\n\n---\n%s" % (text, self._brief(brief_doc))
            images = self._turn_images(state.ws)
            sp, agent = self._turn_args(state.ws, text=text, doc=brief_doc)
            run = claude_cli.ClaudeRun(
                prompt, cwd=state.ws, session_id=state.sid, images=images,
                permission_mode="acceptEdits", system_prompt=sp,
                agent=agent, parent=None)
        except Exception as exc:                       # noqa: BLE001
            _log("could not start the turn: %s" % traceback.format_exc())
            self._busy = False
            self._set_sending(False)
            self.set_backend_state("idle")
            self.show_notice(
                "Could not start the agent",
                "Something went wrong before your message was sent. It is "
                "back in the box below. The details are in the Report view.",
                actions=[("Retry", self._retry_last)],
                detail="%s: %s" % (type(exc).__name__, exc))
            return False
        self._pending_shots = []
        self._shot_captions = {}
        # R184: what a Retry on a stalled turn sends again, and the failure
        # this fix turn started from (R191).
        self._turn_sent = (text, state, bool(fix))
        self._turn_shots = list(images or ())   # R184: a Retry resends them
        self._fix_from = (state.failed, state.failed_intent) if fix \
            else (None, None)
        self._card = ToolCard("Designing", "Claude Code", mono=False)
        self._add(self._card)
        self._build_card = None         # R76: one build card per turn
        self._build_sig = None
        self._turn_failed = False
        self._fix_turn = bool(fix)
        self._last_preview_ok = None
        self._finishing = False
        self._turn_budget = (agent or {}).get("budget")
        self._set_busy(True)
        self._msg_open = False          # R198
        self._tool_fail = None          # R201
        self._heard("model", "")        # R184: the stall clock starts now
        self._build_t = time.monotonic()    # R217: and the no-build clock
        self._quiet_line = ""
        self._stale_preview = False
        self._start_elapsed()           # R101
        run.started_session.connect(self._only(run, self._heard_then(
            self._on_claude_session)))
        # Mid-turn text is the agent working things out ("Let me rewrite",
        # a "Thought process:" dump on a fix turn). It becomes a one-line
        # progress note on the card; only the turn's final answer is a reply.
        run.text.connect(self._only(run, self._heard_then(
            self._on_claude_progress)))
        run.tool.connect(self._only(run, self._heard_then(
            self._on_claude_tool, "tool")))
        run.delta.connect(self._only(run, self._heard_then(
            self._on_claude_delta)))
        run.progress.connect(self._only(run, self._heard_then(
            self._on_claude_writing)))
        activity = getattr(run, "activity", None)
        if activity is not None:
            # R184: every stream event, including the ones the card does
            # not draw (tool results, API retries).
            activity.connect(self._only(run, self._heard))
        opened = getattr(run, "message_open", None)
        if opened is not None:
            opened.connect(self._only(run, self._heard_then(
                self._on_message_open)))
        tool_failed = getattr(run, "tool_failed", None)
        if tool_failed is not None:
            tool_failed.connect(self._only(run, self._on_claude_tool_failed))
        tool_refused = getattr(run, "tool_refused", None)
        if tool_refused is not None:
            # R216: a call refused for want of a permission is drawn as
            # refused on its row, never only logged.
            tool_refused.connect(self._only(run,
                                            self._on_claude_tool_refused))
        run.finished_ok.connect(self._only(run, self._on_claude_done))
        run.failed.connect(self._only(run, self._on_claude_failed))
        self._chat = run
        run.start()
        self._sync_send()
        return True

    def ask(self, text):
        """PUBLIC HOOK: send `text` as if the user typed it (vision's
        ask_in_chat, R36). Respects the busy state and the data notice.
        True when a turn started."""
        text = (text or "").strip()
        if not text:
            return False
        if self._busy:
            self._flash_hint(
                "Still working on the previous message. Press stop to interrupt.")
            return False
        self.input.setPlainText(text)
        self._on_send()
        return bool(self._busy)

    def new_chat(self):
        """R70: a clean conversation for the active document. The transcript
        is cleared, and the document's chat gets a new workspace, no Claude
        session, no previous-build record and a zero fix counter. Bodies
        already in the document stay; R200: when the agent built them from a
        trusted script, the chat's first turn continues from that script
        (_continue_design), otherwise the next build adds beside them."""
        doc = self._active_document()
        key = self._doc_key(doc)
        # R200 (D75): New chat acts on the document being viewed. Right
        # after File > New that is the new document, while the transcript
        # on screen (and a turn still running) may be the one being left:
        # that chat is never stopped, cleared or forgotten from here.
        cur = self._cur
        elsewhere = (self._busy or self._pending is not None) and \
            cur is not None and cur.key != key
        if not elsewhere:
            if self._busy:
                self._on_stop()
            self._cancel_build()
            self._follow_active_doc(draft=True)
        try:
            state = ChatState(key, getattr(doc, "Name", None),
                              build.new_workspace())
        except Exception as exc:                       # noqa: BLE001
            _log("new chat: %r" % (exc,))
            self.show_notice("Could not start a new chat",
                             "No folder could be made for it. The details "
                             "are in the Report view.",
                             detail="%s: %s" % (type(exc).__name__, exc))
            return False
        old = self._docs.get(key)
        if self._needs_review(old):
            # R113: a new chat does not trust the script either; the review
            # stays reachable from the context line (not re-announced).
            state.untrusted = list(self._untrusted_objects(old))
            state.review_offered = True
        # R200: bodies the agent built stay in the document; the first turn
        # of this chat continues from their design (_continue_design).
        state.adopt_on_first_turn = doc is not None
        self._docs[key] = state
        save_session(key, None)
        self._transcripts.pop(key, None)    # R190: a new chat starts empty
        if elsewhere:
            # The other document's turn keeps the screen; this document's
            # chat is new when it is shown next.
            self._sync_review_btn(doc)
            return True
        self._cur = None
        self._attempt = 0
        self._pending_shots = []
        self._shot_captions = {}
        self._last_text = ""
        self._preview_error = ""
        self._preview_intent = None
        self._build_card = None
        self._card = None
        self._clear_transcript()
        # R210: the cleared transcript (and what is typed under it before
        # the document poll runs) is this document's chat.
        self._shown_key = key
        self._show_empty_state(getattr(self, "_connected", True))
        self._sync_review_btn(doc)
        return True

    def _continue_design(self, state, doc):
        """R200 (D75): the first turn of a new chat on a document that
        already holds agent-built bodies starts from their design: the
        newest TRUSTED embedded script (build.adopt checks its sha against
        the trust store, R11) goes into the new workspace as model.py, and
        the previous-build record with it, so the next build replaces those
        bodies instead of adding a second design beside them. An untrusted
        script is never written (the review stays reachable, R113).
        Returns True when a script was adopted."""
        if doc is None or os.path.exists(os.path.join(state.ws,
                                                      build.SCRIPT)):
            return False
        try:
            rec = build.adopt(doc, state.ws)
        except Exception as exc:                       # noqa: BLE001
            _log("new chat adopt: %r" % (exc,))
            return False
        if not rec:
            return False
        if not rec.get("script_adopted"):
            # No script to continue from (the newest one is untrusted): the
            # agent writes a new design, which must not replace the bodies
            # of an older trusted build it never saw - so no previous-build
            # record. The review stays reachable (R113).
            if rec.get("untrusted_script") and state.untrusted is None:
                state.untrusted = list(rec.get("untrusted_objects") or [])
                state.review_offered = True
                self._sync_review_btn(doc)
            return False
        state.prev = rec
        state.good_hash = None          # not built by this chat yet
        state.failed = None
        n = len(rec.get("names") or ())
        _log("new chat on %s: continuing from its design script"
             % getattr(doc, "Name", "?"))
        self.show_notice(
            "Continuing from the design in this document",
            "This chat starts from the script that built %s here, so the "
            "change you asked for edits that design instead of rebuilding "
            "it." % _plural(n, "object"))
        return True

    def _clear_transcript(self):
        """Everything but the trailing stretch goes; the chat states stay."""
        while self.stream.count() > 1:
            item = self.stream.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._empty = self._offline = None
        self._empty_kind = None
        self._privacy_notice = None
        self._crane_notices = []
        self._has_messages = False
        self._shown_key = None

    def _claim_draft(self):
        """R210: text typed while no chat owns the screen (right after New
        chat or at start, before the document poll sets _shown_key) is the
        draft of the document active NOW, when it is typed - not of
        whichever document is active when the poll next runs."""
        if self._shown_key is not None or self._busy or \
                not self.input.toPlainText().strip():
            return
        try:
            self._shown_key = self._doc_key(self._active_document())
        except Exception as exc:                       # noqa: BLE001
            _log("draft owner: %r" % (exc,))

    def _follow_active_doc(self, draft=False):
        """R138 + R190: the transcript on screen belongs to the document
        whose chat the next message goes to. Studio keeps one ChatState per
        document (R17) and, since R190, one transcript per document: when
        the active document is not the one the transcript was written for,
        the transcript on screen is KEPT as data for its document (bubbles,
        cards with their lines and status, notices with their actions,
        queued captures, the last message for Retry) and the active
        document's own kept transcript is drawn again - or its Welcome
        when it has none. Never mid-turn or while a build runs: a running
        turn stays with its own document, and is followed when it ends.
        Returns True when it switched. With `draft` (the document poll) the
        composer's unsent text is kept per document too; a send or a
        capture leaves the box as it is (its text is for the new chat).

        Called on send and add_shot (R138) and from the document poll
        (R144: closing the document, or making another one active, left the
        old chat on screen under a "No document" header)."""
        if self._busy or self._pending is not None:
            return False
        doc = self._active_document()
        key = self._doc_key(doc)
        shown = self._shown_key
        if shown == key:
            return False
        saved = self._transcripts.get(key)
        if shown is None and self._has_messages:
            # Messages no chat owns yet (a notice before the first turn):
            # they are the active document's.
            self._shown_key = key
            return False
        typed = self.input.toPlainText()
        if shown is None and not saved:
            # R199: a Welcome is the active document's too, and so is what
            # is typed under it.
            self._shown_key = key
            return False
        if not self._has_messages and not saved and \
                not (draft and typed.strip()):
            # Nothing to keep: the Welcome on screen is now the active
            # document's (R199: so a draft typed under it is kept for it).
            self._shown_key = key
            return False
        _log("transcript of %s -> the active document's chat" % shown)
        state = self._docs.get(key)
        pending = self._review_pending(state)
        # A view of THIS document captured while the other chat's turn was
        # still running was queued behind that turn: it belongs to this
        # chat (capture_path writes into this document's workspace), so it
        # is kept and shown again, not dropped with the other chat's views.
        ws = os.path.abspath(state.ws) if state is not None else None
        mine = [p for p in self._pending_shots if ws and
                os.path.dirname(os.path.abspath(p)) == ws]
        captions = dict(self._shot_captions)
        if shown is not None:
            if self._has_messages or (draft and typed.strip()):
                kept = self._snapshot(shown, skip=mine)
                kept["draft"] = typed if draft else ""
                self._transcripts[shown] = kept
            else:
                self._transcripts.pop(shown, None)
        self._clear_transcript()
        self._pending_shots = []
        self._shot_captions = {}
        self._last_text = ""
        self._build_card = None
        self._card = None
        self._shown_key = key
        kept = self._transcripts.pop(key, None)
        restored = self._restore(kept)
        if draft:
            self.input.setPlainText((kept or {}).get("draft") or "")
            self.input.moveCursor(QtGui.QTextCursor.End)
        if pending and not self._review_pending(state):
            # R98: the active document's own script review was posted into
            # the old transcript when it opened; it stays in front of the
            # user, now in its own chat.
            state.review_offered = False
            self._offer_review(state, doc)
        for p in mine:
            self.add_shot(p, captions.get(p, ""))
        if restored:
            self._follow = True
            QtCore.QTimer.singleShot(0, self._scroll_bottom)
        return True

    # --------------------------------------- per-document transcript (R190)
    _STATUS_KIND = {"StatusRun": "run", "StatusOk": "ok",
                    "StatusFail": "fail", "StatusIdle": "idle"}

    def _snapshot(self, owner, skip=()):
        """The transcript on screen as data, for document `owner` (R190).

        The Welcome, the offline notice and the data notice are the panel's
        own, not the chat's, and are left out; so is another document's
        script review (it goes back to that document) and a capture that
        belongs to the chat being switched to (`skip`)."""
        entries = []
        review_of = {}
        for st in self._docs.values():
            n = getattr(st, "review_notice", None)
            if n is not None:
                review_of[id(n)] = st.key
        skip = set(skip or ())
        for i in range(self.stream.count()):
            w = self.stream.itemAt(i).widget()
            if w is None or w.isHidden() or w is self._empty or \
                    w is self._offline or \
                    w is getattr(self, "_privacy_notice", None):
                continue
            if isinstance(w, Bubble):
                entries.append({"kind": "bubble", "text": w.raw_text,
                                "role": w.role})
            elif isinstance(w, ToolCard):
                name, args, mono = w.spec
                entries.append({
                    "kind": "card", "name": name, "args": args, "mono": mono,
                    "body": w.body.text() if not w.body.isHidden() else "",
                    "status": w.status.text(),
                    "status_kind": self._STATUS_KIND.get(
                        w.status.objectName(), "idle"),
                    "tip": w.status.toolTip(),
                    "caveat": w.caveat, "caveat_text": w.caveat_text,
                    "info_text": w.info_text})
            elif isinstance(w, Notice):
                title, body, actions, detail = w.spec
                tag = None
                if id(w) in review_of:
                    if review_of[id(w)] != owner:
                        continue            # another document's review
                    tag = ("review", review_of[id(w)])
                elif w is getattr(self, "_budget_notice", None):
                    tag = ("budget", None)
                entries.append({
                    "kind": "notice", "title": title, "body": body,
                    "actions": list(actions), "detail": detail, "tag": tag,
                    "enabled": [b.isEnabled() for b in w.buttons]})
            elif isinstance(w, Shot):
                path, caption = w.spec
                if path in skip:
                    continue
                entries.append({"kind": "shot", "path": path,
                                "caption": caption})
            else:
                _log("transcript: %s not kept" % type(w).__name__)
        return {"entries": entries,
                "shots": [p for p in self._pending_shots if p not in skip],
                "captions": dict(self._shot_captions),
                "last_text": self._last_text}

    def _restore(self, kept):
        """Draw a document's kept transcript again (R190). Returns the
        number of entries drawn."""
        if not kept:
            return 0
        entries = kept.get("entries") or []
        if entries:
            self._clear_empty()
            self._has_messages = True
        for e in entries:
            kind = e.get("kind")
            if kind == "bubble":
                self._add(Bubble(e["text"], e["role"]))
            elif kind == "card":
                c = ToolCard(e["name"], e["args"], mono=e["mono"])
                if e.get("body"):
                    c.append(e["body"])
                c.set_status(e["status"], e["status_kind"])
                if e.get("tip"):
                    c.status.setToolTip(e["tip"])
                c.caveat = e.get("caveat") or ""
                if e.get("caveat_text") or e.get("info_text"):
                    c.set_notes(e.get("caveat_text"), e.get("info_text"))
                self._add(c)
            elif kind == "notice":
                n = self._add(Notice(e["title"], e["body"],
                                     actions=e["actions"],
                                     detail=e["detail"]))
                for b, on in zip(n.buttons, e.get("enabled") or ()):
                    b.setEnabled(on)
                tag = e.get("tag")
                if tag and tag[0] == "review":
                    st = self._docs.get(tag[1])
                    if st is not None:
                        st.review_notice = n
                elif tag and tag[0] == "budget":
                    self._budget_notice = n
                if e["title"] in CRANE_NOTICE_TITLES:
                    self._crane_notices.append(n)
                    self._pill_sig = None
            elif kind == "shot":
                self._add(Shot(e["path"], e["caption"]))
        self._pending_shots = [p for p in kept.get("shots") or ()
                               if os.path.isfile(p)]
        self._shot_captions = dict(kept.get("captions") or {})
        self._last_text = kept.get("last_text") or ""
        return len(entries)

    @staticmethod
    def _review_pending(state):
        """The state's review notice is on screen and not answered yet."""
        n = getattr(state, "review_notice", None) if state else None
        if n is None:
            return False
        try:
            return any(b.isEnabled() for b in getattr(n, "buttons", []))
        except RuntimeError:                           # notice deleted
            return False

    def _retry_last(self):
        """Retry on a failure notice: send the last message again (R23)."""
        text = self._last_text
        if not text:
            self._probe_backend_again()
            return
        if self._busy:
            self._flash_hint(
                "Still working on the previous message. Press stop to interrupt.")
            return
        if engine.current() != engine.CLAUDE:
            self.input.setPlainText(text)
            self._on_send()
            return
        if self.input.toPlainText().strip() == text:
            self.input.clear()
        self._attempt = 0
        if not self._send_claude(text):
            self._restore_input()

    @property
    def _ws(self):
        """The workspace of the current turn (compat for older callers)."""
        return self._cur.ws if self._cur is not None else None

    #: Live-preview debounce (S02). MEASURED 2026-09-25 with the real
    #: watcher offscreen and a synthetic agent (4 rounds of a Write split
    #: 300 ms mid-file, then 3 Edits 200 ms apart; build.apply counted):
    #:   debounce            150 ms   250 ms   400 ms
    #:   mtime only          20 (4)   8 (4)    4 (0)   previews (half-written)
    #:   hash + compile gate 17 (1)   5 (1)    4 (0)
    #:   same, identical rewrites: gate 5/5/4 vs mtime 20/8/4
    #: 400 ms has the fewest failed previews; the gate is what removes the
    #: waste at shorter settings. (A truncation that still parses, e.g.
    #: "box = P", passes any compile gate.)
    PREVIEW_DEBOUNCE_MS = 400

    def _watch_workspace(self):
        if getattr(self, "_watcher", None) is None:
            self._watcher = QtCore.QFileSystemWatcher(self)
            self._watch_timer = QtCore.QTimer(self)
            self._watch_timer.setSingleShot(True)
            self._watch_timer.setInterval(self.PREVIEW_DEBOUNCE_MS)
            self._watch_timer.timeout.connect(self._on_ws_changed)
            self._watcher.directoryChanged.connect(
                lambda _p: self._watch_timer.start())
            self._watcher.fileChanged.connect(
                lambda _p: self._watch_timer.start())
        ws = self._ws
        stale = [d for d in self._watcher.directories() if d != ws]
        if stale:
            self._watcher.removePaths(stale)
        stale = [f for f in self._watcher.files()
                 if os.path.dirname(f) != ws]
        if stale:
            self._watcher.removePaths(stale)
        if ws not in self._watcher.directories():
            self._watcher.addPath(ws)
        script = os.path.join(ws, build.SCRIPT)
        if os.path.exists(script) and script not in self._watcher.files():
            self._watcher.addPath(script)

    @staticmethod
    def _script_hash(ws):
        """sha1 of model.py's bytes, or None when there is none (S02)."""
        try:
            with open(os.path.join(ws, build.SCRIPT), "rb") as fh:
                return hashlib.sha1(fh.read()).hexdigest()
        except OSError:
            return None

    @staticmethod
    def _compiles(path):
        """build.compiles (WS-BUILD, S01) when it exists, else the same
        check here: does the file parse as Python?"""
        fn = getattr(build, "compiles", None)
        if callable(fn):
            try:
                return bool(fn(path))
            except Exception:                          # noqa: BLE001
                return False
        try:
            with open(path, encoding="utf-8") as fh:
                compile(fh.read(), path, "exec")
            return True
        except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
            return False

    def _preview_files(self):
        """Files worth a live preview now (S02): changed since the last
        build, and for model.py only when its CONTENT changed (an Edit that
        leaves it identical, or a touch, is not a rebuild) and it compiles
        (a half-written script is not built)."""
        files = build.changed(self._ws, self._applied)
        if build.SCRIPT not in files:
            return files
        h = self._script_hash(self._ws)
        script = os.path.join(self._ws, build.SCRIPT)
        if h is None or h == self._preview_hash or \
                not self._compiles(script):
            self.stats["previews_skipped"] += 1
            files = [f for f in files if f != build.SCRIPT]
            if h == self._preview_hash:
                # Same bytes, new mtime: remember the mtime so the end of
                # the turn does not rebuild it either.
                self._applied[build.SCRIPT] = build.snapshot(self._ws).get(
                    build.SCRIPT)
            return files
        self._preview_hash = h
        return files

    def _on_ws_changed(self):
        """Mid-turn: show what the agent just wrote, right away."""
        if self._stopped or not self._busy or self._cur is None or \
                self._finishing:
            return                      # the end of the turn handles it
        if self._pending is not None:
            # One build at a time (R93): look again when this one ends.
            self._preview_again = True
            return
        self._watch_workspace()         # a rewritten file drops its watch
        files = self._preview_files()
        if files:
            self._applied = build.snapshot(self._ws)
            self._run_build(files, preview=True)

    def _on_claude_session(self, sid):
        if self._cur is not None:
            self._cur.sid = sid
            self._remember(self._cur)
        try:
            flags = self._chat.flags() if self._chat is not None else None
            if flags:
                _log("claude argv: %s" % " ".join(flags))
            dropped = getattr(self._chat, "dropped", None)
            if dropped:
                _log("flags this claude does not support (not passed): %s"
                     % ", ".join(dropped))
                # R78 is a privacy promise: when the installed CLI cannot
                # keep the agent out of the user's own MCP servers and
                # settings, say so on the turn instead of only in the log.
                lost = [f for f in ("--strict-mcp-config", "--setting-sources")
                        if f in dropped]
                if lost and self._card:
                    self._card.append(
                        "⚠ this Claude Code cannot isolate the agent (%s "
                        "unsupported): it may use your own Claude settings "
                        "and connectors. Update Claude Code."
                        % ", ".join(lost))
        except Exception:                              # noqa: BLE001
            pass

    def _on_claude_progress(self, text):
        if not self._card:
            return
        self._card.set_progress("")
        line = " ".join(text.split())
        if line.lower().startswith("thought process:"):
            line = line[len("thought process:"):].strip()
        if not line:
            return
        self._card.append("… " + (line if len(line) <= 90 else line[:89] + "…"),
                          keep=6)

    def _on_claude_delta(self, text):
        """S19: the assistant block streamed so far, on the card's live
        line (the finished block is appended as a progress note)."""
        if not self._card:
            return
        line = " ".join(text.split())
        if line:
            self._card.set_progress(line if len(line) <= 90
                                    else "…" + line[-89:])

    def _on_claude_writing(self, text):
        """S19: 'writing model.py: N lines' while the Write streams in."""
        if self._card:
            self._card.set_progress(text)

    def _on_claude_tool(self, name, arg):
        if self._card:
            self._card.set_progress("")
            self._card.append("%s  %s" % (name, arg), keep=6)

    @staticmethod
    def _denials(record):
        """'Bash ls ~' lines for the permission_denials of a result (S16)."""
        out = []
        for d in record.get("permission_denials") or ():
            if not isinstance(d, dict):
                continue
            from . import claude_cli
            out.append(("%s %s" % (d.get("tool_name") or "tool",
                                   claude_cli._summarise(
                                       d.get("tool_input"), 70))).strip())
        return out

    def _on_claude_done(self, final, record):
        self._stop_elapsed()
        if self._card:
            self._card.set_progress("")
            secs = (record.get("duration_ms") or 0) / 1000.0
            cost = record.get("total_cost_usd")
            # Duration only by default: on a subscription the CLI still
            # reports an API-equivalent dollar figure nobody pays (R26).
            show_cost = bool(cfgmod.load().get("show_cost"))
            self._card.set_status(
                "%.0fs%s" % (secs, (" · $%.2f" % cost)
                             if cost and show_cost else ""), "ok")
        # S16 enforces the allowlist; R125 (D48): the agent's refused
        # exploratory commands (`cd … && sed`, `ls` outside the workspace)
        # read to users as an error on a turn that succeeded. They go to
        # the Report view, not the card. The S16 isolation warning (a CLI
        # that cannot isolate the agent) stays on the card.
        denied = self._denials(record)
        if denied:
            _log("agent actions refused by the allowlist (%d): %s"
                 % (len(denied), "; ".join(denied[:20])))
        card = self._card
        self._card = None
        self._remember(self._cur)
        final = (final or "").strip()
        if self._stopped:
            self._end_turn()
            if final:
                self.say(final)
            return
        # R93: the turn stays "working" (Stop still works) until its final
        # build is in; no live preview starts after this point.
        self._finishing = True
        if self._pending is not None:
            # A live preview is still building: finish the turn after it.
            self._after_build = functools.partial(self._finish_turn, final,
                                                  card)
            return
        self._finish_turn(final, card)

    def _finish_turn(self, final, card):
        """The end of a turn, after any live preview in flight: build what
        changed since the last build, then show the reply (R75, R93)."""
        self._after_build = None
        state = self._cur
        # R75: build FIRST, then decide how the agent's words are shown. A
        # "Built a pinion" bubble must not stand above a failed build.
        files = build.changed(self._ws, getattr(self, "_applied", self._before))
        h = self._script_hash(self._ws)
        if build.SCRIPT in files and \
                getattr(self, "_previewed_ok", None) is not None and \
                h == self._previewed_ok and \
                not getattr(self, "_preview_error", ""):
            # S02: the final script is the one the live preview already
            # built successfully - do not build it twice.
            files = [f for f in files if f != build.SCRIPT]
        if files:
            self._applied = build.snapshot(self._ws)
            self._run_build(files, then=functools.partial(
                self._reply, final, card))
            return
        fix = None
        last = getattr(self, "_last_preview_ok", None)
        pending = getattr(self, "_preview_intent", None)
        if pending is not None and h is not None and \
                h == getattr(self, "_preview_intent_hash", None) and \
                not getattr(self, "_preview_error", ""):
            # S49: the last preview was short of intent.json only, shown as
            # "in progress", and nothing changed since. That result IS the
            # turn's final build: settled as one, intent.json is enforced
            # here (check failed + a fix turn when still missed).
            self._preview_intent = None
            fix = self._settle(state, pending, preview=False, built_hash=h)
        elif getattr(self, "_preview_error", ""):
            # The last live preview failed and the agent never rewrote the
            # script: that failure is the turn's result - send it back.
            err, self._preview_error = self._preview_error, ""
            self._turn_failed = True
            fix = self._fix_message(err)
        elif last is not None and h is not None and h == self._previewed_ok:
            # The final script is the one a live preview built: the
            # end-of-turn part (fine mesh, the Atech check) runs on that
            # result, once (R94).
            fix = self._settle(state, last, preview=False, built_hash=h)
        elif getattr(self, "_fix_turn", False) and state is not None and \
                state.failed and h is not None and state.failed[0] == h:
            # R98/R75 edge: a fix turn that left model.py exactly as it
            # failed. Its reply is not a success; the measured failure of
            # this very script stands and goes back as the next fix.
            self._turn_failed = True
            fix = state.failed[1]
            target = self._turn_card(False)
            target.set_status("unchanged: still fails", "fail")
        self._reply(final, card, fix)

    def _reply(self, final, card, fix):
        """Show the agent's final words - demoted into the build card when
        the turn's build failed (R75) - and send a fix turn if one is due."""
        if fix and self._disputed_check():
            self._not_confirmed(final, card)
            return
        self._end_turn()
        if final:
            if self._turn_failed:
                target = self._build_card or card
                if target is not None:
                    target.append("Agent: " + (final if len(final) <= 300
                                               else final[:299] + "…"))
                else:
                    self.say("Build failed checks, fixing. " + final)
            else:
                self.say(final)
        if fix:
            self._send_fix(fix)

    #: R191: the card line and note when a fix turn leaves model.py as it
    #: was and only intent.json misses remain.
    NOT_CONFIRMED_LINE = "could not confirm: intent.json targets"
    NOT_CONFIRMED_NOTE = (
        "The check could not confirm %s. The agent left model.py unchanged, "
        "so no further fix was sent. The part is "
        "built: compare it in the view, or say what is wrong.")

    def _disputed_check(self):
        """R191 (D74): a fix turn that left model.py exactly as it failed,
        when that failure was intent.json misses only. The agent disputes
        the check rather than the part; sending the same misses back again
        ends on a red "Tried 2 fixes" under a part that may be correct."""
        if not getattr(self, "_fix_turn", False):
            return False
        state = self._cur
        failed, intent = getattr(self, "_fix_from", (None, None))
        if state is None or not failed or not intent:
            return False
        h = self._script_hash(state.ws)
        if h is None or h != failed[0]:
            return False                # the agent changed the script
        # What this turn measured (its own build, or the unchanged failure
        # standing) must still be short of intent.json only.
        return bool(state.failed_intent)

    def _not_confirmed(self, final, card):
        """R191: finish neutrally - no red status, no fix, no notice."""
        state = self._cur
        problems = list((state.failed_intent if state is not None else None)
                        or self._fix_from[1] or [])
        self._turn_failed = False
        self._attempt = 0
        target = self._turn_card(False)
        target.append(self.NOT_CONFIRMED_LINE)
        target.set_status("not confirmed", "idle")
        what = "; ".join(str(p) for p in problems[:3]) or \
            "the intent.json targets"
        if len(what) > 240:
            what = what[:239] + "…"
        target.set_notes(target.caveat, self.NOT_CONFIRMED_NOTE % what)
        _log("fix turn left model.py unchanged; intent-only misses not "
             "confirmed: %s" % "; ".join(str(p) for p in problems))
        self._end_turn()
        if final:
            self.say(final)

    def _end_turn(self):
        self._finishing = False
        self._busy = False
        self._set_sending(False)
        self.set_backend_state("idle")

    # ------------------------------------------------- elapsed time (R101)
    @staticmethod
    def _elapsed_text(secs):
        secs = int(max(0, secs))
        if secs < 60:
            return "%ds" % secs
        return "%dm %02ds" % (secs // 60, secs % 60)

    def _start_elapsed(self):
        """The Designing card counts up while the agent works (R101): a
        turn that runs for minutes must say so, not sit on "working"."""
        self._turn_t0 = time.monotonic()
        if getattr(self, "_tick", None) is None:
            self._tick = QtCore.QTimer(self)
            self._tick.setInterval(1000)
            self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self._on_tick()

    def _on_tick(self):
        if self._card is None:
            return
        self._check_stall()             # R184
        txt = "working " + self._elapsed_text(
            time.monotonic() - getattr(self, "_turn_t0", time.monotonic()))
        budget = getattr(self, "_turn_budget", None)
        if budget:
            self._card.status.setToolTip(
                "Stops at the %s limit for one message (Settings > "
                "Budget per reply)" % self._money(budget))
        self._card.set_status(txt, "run")

    def _stop_elapsed(self):
        t = getattr(self, "_tick", None)
        if t is not None:
            t.stop()
        # R184: a turn that ended (reply, failure, Stop) waits on nothing.
        if self._card is not None:
            try:
                self._card.set_stall("")
            except RuntimeError:                       # card deleted
                pass

    # --------------------------------------------- stall watchdog (R184)
    #: Seconds without a stream event before the card says it is waiting.
    #: Eval r8 measured silent gaps of 142-846 s (S57) against a median
    #: final time of 52 s; a minute of nothing is already unusual, while a
    #: model thinking before a long Write stays under it. The run is never
    #: killed from here: the turn timeout still decides that.
    STALL_AFTER_S = 60

    def _heard(self, kind="model", detail=""):
        """A stream event arrived (R184): restart the stall clock, and take
        the waiting line off the card. `kind` is what the turn waits on
        next: "model", "tool" (a tool call is running, `detail` names it)
        or "retry" (the CLI is retrying the API, `detail` = attempt)."""
        self._last_event_t = time.monotonic()
        self._waiting_on = (kind or "model", detail or "")
        card = self._card
        if card is not None:
            try:
                # R217: events keep coming while no build advances; the
                # no-build line is not about silence, so they leave it.
                line = card.stall_text()
                if line and line != getattr(self, "_quiet_line", ""):
                    card.set_stall("")
            except RuntimeError:                       # card deleted
                pass

    def _heard_then(self, handler, kind="model"):
        """A run signal's slot that also counts as a stream event."""
        def slot(*args):
            if kind == "tool" and args:
                self._heard("tool", " ".join(str(a) for a in args[:2]))
            else:
                self._heard(kind)
            handler(*args)
        return slot

    def _on_message_open(self, on):
        """R198: the model has a message open (True) or not."""
        self._msg_open = bool(on)

    def _on_claude_tool_failed(self, name, arg, reason):
        """R201 (D76): a tool call came back is_error. Its row on the card
        says so; the stall line, if the model then goes quiet, names it."""
        self._tool_fail = (name, arg, reason)
        self._heard("failed", ("%s %s" % (name, arg)).strip())
        _log("tool call failed: %s %s: %s" % (name, arg, reason))
        if self._card:
            self._card.set_progress("")
            self._card.mark_failed("%s  %s" % (name, arg), reason)

    def _on_claude_tool_refused(self, name, arg, reason):
        """R216 (S7 c1r77): the CLI refused a tool call for want of a
        permission - a Read outside the chat's one --add-dir. It never
        ran; the agent is told so and carries on, so the row says it was
        refused (in the failure colour, R205) rather than leaving a
        permission request the user never sees."""
        self._tool_fail = (name, arg, reason)
        self._heard("failed", ("%s %s" % (name, arg)).strip())
        _log("tool call refused: %s %s: %s" % (name, arg, reason))
        if self._card:
            self._card.set_progress("")
            self._card.mark_failed("%s  %s" % (name, arg), reason,
                                   verb="refused")

    def _still_working(self):
        """R198: the silence is the model producing an open message (no
        API retry since it opened): Retry would discard its reasoning."""
        kind = getattr(self, "_waiting_on", ("model", ""))[0]
        return bool(getattr(self, "_msg_open", False)) and kind != "retry"

    def stall_line(self, quiet):
        """The card's waiting line after `quiet` seconds of silence."""
        kind, detail = getattr(self, "_waiting_on", ("model", ""))
        t = self._elapsed_text(quiet)
        if self._still_working():
            return ("the model is still working · %s with no output yet"
                    % t)
        if kind == "failed":
            fail = getattr(self, "_tool_fail", None)
            what = (detail or "a tool call").strip()
            if fail and fail[2]:
                what = "%s: %s" % (what, fail[2])
            if len(what) > 90:
                what = what[:89] + "…"
            return ("the last tool call failed (%s) · waiting on the model "
                    "· %s with no reply" % (what, t))
        if kind == "tool":
            what = (detail or "a tool call").strip()
            if len(what) > 60:
                what = what[:59] + "…"
            return "waiting on %s · %s with no reply" % (what, t)
        if kind == "retry":
            return ("waiting on the model · %s; the API is being retried%s"
                    % (t, " (attempt %s)" % detail if detail else ""))
        return "waiting on the model · %s with no reply" % t

    def _check_stall(self):
        """Called every second with the elapsed tick (R184)."""
        card = self._card
        if card is None or not self._busy or self._stopped:
            return
        t0 = getattr(self, "_last_event_t", None)
        if t0 is None:
            return
        quiet = time.monotonic() - t0
        if quiet < self.STALL_AFTER_S:
            self._check_build_quiet(card)       # R217
            return
        self._quiet_line = ""
        try:
            if self._still_working():
                # R198: no Retry - only Stop.
                card.set_stall(self.stall_line(quiet), None, self._on_stop)
            else:
                card.set_stall(self.stall_line(quiet), self._retry_stalled,
                               self._on_stop)
        except RuntimeError:
            pass

    # ------------------------------------------ no-build notice (R217)
    #: Seconds a turn may run without a preview or build advancing before
    #: the card says so. MEASURED (S7 c1r77, c2r77): hinge turns ran 799 s
    #: and 896 s with 2-6 min between tool calls - events kept arriving,
    #: so the R184 silence watchdog never spoke, and the card sat on a
    #: stale "preview: in progress" for minutes. Eval r10: median final
    #: 51 s (n=12), so 5 minutes without a new build is far outside a
    #: normal turn.
    BUILD_QUIET_S = 300
    PREVIEW_IN_PROGRESS = "preview: in progress"

    def build_quiet_line(self, quiet):
        """The card line after `quiet` seconds with no build advancing."""
        return ("Still working · no new build for %d min"
                % max(1, int(quiet // 60)))

    def _build_advanced(self):
        """R217: a preview or build started or landed: restart the
        no-build clock and take its line off the card."""
        self._build_t = time.monotonic()
        self._stale_preview = False
        card, line = self._card, getattr(self, "_quiet_line", "")
        self._quiet_line = ""
        if card is not None and line:
            try:
                if card.stall_text() == line:
                    card.set_stall("")
            except RuntimeError:                       # card deleted
                pass

    def _check_build_quiet(self, card):
        """R217, every tick while no silence line shows: after
        BUILD_QUIET_S with no build advancing (and none in flight), a
        "Still working" line with Stop; and a build card still saying
        "preview: in progress" says how old that preview is instead - no
        preview is in progress."""
        t = getattr(self, "_build_t", None)
        line = getattr(self, "_quiet_line", "")
        if t is None or self._pending is not None:
            if line:
                self._build_advanced()
            return
        quiet = time.monotonic() - t
        if quiet < self.BUILD_QUIET_S:
            if line:
                self._build_advanced()
            return
        text = self.build_quiet_line(quiet)
        try:
            if card.stall_text() != text:
                card.set_stall(text, None, self._on_stop)
            self._quiet_line = text
        except RuntimeError:
            return
        bc = self._build_card
        try:
            if bc is not None and (
                    getattr(self, "_stale_preview", False) or
                    bc.status.text() == self.PREVIEW_IN_PROGRESS):
                self._stale_preview = True
                bc.set_status("last preview %s ago"
                              % self._elapsed_text(quiet), "idle")
        except RuntimeError:                           # card deleted
            self._build_card = None

    def _retry_stalled(self):
        """Retry on the waiting line: stop the silent run and send the same
        message again, in the same chat and Claude session. Only when the
        user asks - the watchdog itself never stops a run."""
        sent = getattr(self, "_turn_sent", None)
        if not self._busy or not sent:
            return False
        text, state, fix = sent
        typed = self.input.toPlainText()
        queued = (list(self._pending_shots), dict(self._shot_captions))
        self._on_stop()
        # _on_stop puts the last message back in the box; this retry sends
        # it itself, so the box keeps only what the user had typed.
        self.input.setPlainText(typed)
        # The views the stalled turn was sent with go again (captures
        # queued since then stay queued for the next message).
        self._pending_shots = list(getattr(self, "_turn_shots", ()) or ())
        _log("stalled turn retried by the user")
        try:
            return self._send_claude(text, state=state, fix=fix)
        finally:
            self._pending_shots, self._shot_captions = queued

    @staticmethod
    def _money(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "$?"
        return "$%d" % v if abs(v - round(v)) < 1e-9 else "$%.2f" % v

    def _activate_state_doc(self, state):
        """Build into the document the turn was sent from, not whichever one
        is active when the turn ends (R17)."""
        doc = self._state_doc(state)
        if doc is None:
            return
        try:
            import FreeCAD
            if FreeCAD.ActiveDocument is not doc:
                FreeCAD.setActiveDocument(doc.Name)
        except Exception as exc:                       # noqa: BLE001
            _log("activate %s: %r" % (state.doc_name, exc))

    def _rekey(self, state, doc_name):
        """A chat started with no document owns the one its build created."""
        if state.key != NO_DOC or not doc_name:
            return
        try:
            import FreeCAD
            doc = FreeCAD.getDocument(doc_name)
        except Exception:                              # noqa: BLE001
            return
        key = self._doc_key(doc)
        if key in self._docs and self._docs[key] is not state:
            return
        self._docs.pop(NO_DOC, None)
        state.key, state.doc_name = key, doc.Name
        self._docs[key] = state
        if self._shown_key == NO_DOC:
            self._shown_key = key           # R138: still this chat

    def _doc_was_closed(self, state):
        """R81: the turn's document was closed. A chat with no document yet
        (NO_DOC) has nothing to lose; its first build makes one."""
        return state is not None and state.key != NO_DOC and \
            self._state_doc(state) is None

    def _on_doc_closed_mid_turn(self, state):
        """R81: never build into a new "Untitled" because the chat's own
        document went away. Stop the turn and say so."""
        if self._busy:
            self._on_stop()
        self._turn_failed = True
        self.show_notice(
            "The document was closed",
            "%s was closed while the agent was working, so the result was "
            "not built. The design script is kept; open the document again "
            "and ask to rebuild it." % (state.doc_name or "The document"))

    def _fix_message(self, err):
        """The message a fix turn starts with (R74)."""
        fn = getattr(build, "fix_report", None)
        if callable(fn):
            try:
                body = fn(build.Result(False, build.SCRIPT, error=err))
                if body:
                    return "The script failed when Atech Atelier ran it:\n%s" \
                        % body
            except Exception as exc:                   # noqa: BLE001
                _log("fix_report: %r" % (exc,))
        return "The script failed when Atech Atelier ran it:\n%s" \
            % _fix_report(err)

    def _turn_card(self, preview):
        """R76: ONE build card per turn, updated in place."""
        card = self._build_card
        try:
            alive = card is not None and card.parent() is not None
        except RuntimeError:            # deleted (New chat)
            alive = False
        if not alive:
            card = ToolCard("Building the model",
                            "live preview" if preview else "")
            self._add(card)
            self._build_card = card
        return card

    #: How often the GUI polls a build in flight (R93). The sandboxed child
    #: runs in its own process; poll() only checks it, so the event loop
    #: never waits on the build.
    BUILD_POLL_MS = 40

    def _run_build(self, files, preview=False, send_fix=True, then=None):
        """Start building `files` into the turn's document, WITHOUT blocking
        the GUI thread (R93): build.start() returns a PendingBuild that a
        QTimer polls; the result is handled in _build_done.

        One build at a time. A live preview asked for while one runs is
        retried when it ends. `then(fix)` - the end of a turn - is called
        with the fix message (or None) once the build is in; without it a
        failed final build sends its own fix turn when send_fix is True."""
        state = self._cur
        if self._doc_was_closed(state):
            self._on_doc_closed_mid_turn(state)
            if then is not None:
                then(None)
            return None
        if self._pending is not None:
            if preview:
                self._preview_again = True
                return None
            # A final build while a preview runs: _on_claude_done defers
            # the turn end, so this only happens if a caller skipped that.
            _log("build requested while another is in flight; queued")
            self._after_build = functools.partial(
                self._run_build, files, preview, send_fix, then)
            return None
        if preview:
            self.stats["previews"] += 1
        ctx = {"state": state, "files": list(files), "preview": preview,
               "send_fix": send_fix, "then": then,
               "built_hash": self._script_hash(state.ws)
               if build.SCRIPT in files else None,
               "t0": time.monotonic()}
        self._activate_state_doc(state)
        try:
            pending = self._start(state, files, preview)
            res = pending.poll() if pending is not None else None
        except BaseException as exc:                   # noqa: BLE001
            _log("build crashed: %s" % traceback.format_exc())
            pending, res = None, build.Result(False, files[0], error=repr(exc))
        if pending is None or res is not None:
            self._build_done(ctx, res)
            return None
        self._pending = (pending, ctx)
        self._build_advanced()          # R217
        self._turn_card(preview).set_status("building", "run")
        if getattr(self, "_build_timer", None) is None:
            self._build_timer = QtCore.QTimer(self)
            self._build_timer.setInterval(self.BUILD_POLL_MS)
            self._build_timer.timeout.connect(self._poll_build)
        self._build_timer.start()
        return None

    def _poll_build(self):
        """QTimer slot: is the build in flight done? Never blocks."""
        if self._pending is None:
            self._build_timer.stop()
            return
        pending, ctx = self._pending
        try:
            res = pending.poll()
        except BaseException as exc:                   # noqa: BLE001
            _log("build crashed: %s" % traceback.format_exc())
            res = build.Result(False, ctx["files"][0], error=repr(exc))
        if res is None:
            card = self._build_card
            secs = time.monotonic() - ctx["t0"]
            if card is not None and secs >= 1.0:
                try:
                    card.set_status("building " + self._elapsed_text(secs),
                                    "run")
                except RuntimeError:                   # card deleted
                    pass
            return
        self._pending = None
        self._build_timer.stop()
        self._build_done(ctx, res)

    def _cancel_build(self):
        """Stop / New chat: kill the build in flight; the document keeps
        the last good build (build.PendingBuild.cancel)."""
        pb, self._pending = self._pending, None
        self._after_build = None
        self._preview_again = False
        t = getattr(self, "_build_timer", None)
        if t is not None:
            t.stop()
        if pb is not None:
            try:
                pb[0].cancel()
            except Exception as exc:                   # noqa: BLE001
                _log("cancel build: %r" % (exc,))
            if self._build_card is not None:
                try:
                    self._build_card.set_status("cancelled", "idle")
                except RuntimeError:
                    pass

    def _build_done(self, ctx, res):
        """A build is in (or there was nothing to build)."""
        state, preview = ctx["state"], ctx["preview"]
        if res is not None:
            self._build_advanced()      # R217: a build landed
        fix = None
        if res is not None and not res.ok and self._doc_was_closed(state):
            # R81 + R93: the document went away while the sandboxed child
            # ran. build.sandboxed() reports that as a failed build; it is
            # not the agent's bug, so it must never become a fix turn.
            self._on_doc_closed_mid_turn(state)
            then = ctx["then"]
            if then is not None:
                then(None)
            self._next_build()
            return
        if res is None:
            if self._build_card is None:
                self._turn_card(preview).set_status("nothing to build",
                                                    "idle")
        else:
            fix = self._settle(state, res, preview, ctx["built_hash"])
        then = ctx["then"]
        if fix and not preview and then is None and ctx["send_fix"]:
            self._send_fix(fix)
        elif then is not None:
            then(None if preview else fix)
        self._next_build()

    def _next_build(self):
        """What waited on the build that just ended: the end of the turn,
        or a live preview asked for meanwhile."""
        if self._pending is not None:
            return
        after, self._after_build = self._after_build, None
        if after is not None:
            after()
            return
        if self._preview_again:
            self._preview_again = False
            QtCore.QTimer.singleShot(0, self._on_ws_changed)

    def _settle(self, state, res, preview, built_hash):
        """Card, checks and view for one build result. Returns the fix
        message of a failed FINAL build, else None.

        The final build (not a preview) gets the Atech port check, once
        (R94, S22), before its failures are read, and the fine mesh."""
        if not preview and res.ok:
            self._atech_check(res)
        lines, fix, status = self._build_lines(res, preview)
        sig = (bool(res.ok), tuple(lines), status)
        card = self._turn_card(preview)
        if sig != self._build_sig:
            # Updated in place, and only when the result changed (R76).
            self._build_sig = sig
            card.clear()
            for ln in lines:
                card.append(ln)
        card.set_status(*status)
        # R127: build.isolation_warning sets res.warning once per session
        # per isolation mode (R115): the first build without bwrap says so
        # on its card, not only in the Report view.
        # R174: the in-progress explanation shares the note: it is shown
        # for this result only, the caveat for the rest of the turn.
        # R186: the caveat in the warning style, the explanation muted.
        warn = getattr(res, "warning", "") or ""
        if warn:
            card.caveat = warn
        notes = (getattr(card, "caveat", "") or "",
                 getattr(self, "_progress_note", "") or "")
        if notes != (card.caveat_text, card.info_text):
            card.set_notes(*notes)
        if preview and getattr(self, "_preview_intent", None) is res:
            # S49: which script that in-progress preview built.
            self._preview_intent_hash = built_hash
        if res.ok and status[1] == "ok" and built_hash is not None:
            # S02: this exact script built cleanly.
            state.good_hash = built_hash
            if preview:
                self._previewed_ok = built_hash
                self._last_preview_ok = res
        if res.ok:
            state.prev = res.record()
            self._rekey(state, res.doc)
            self._remember(state)
            self._frame(state, res, preview)
            self.refresh_doc_pill()
        if not preview:
            # R98: what the script on disk measured, for a fix turn that
            # leaves it unchanged.
            state.failed = (built_hash, fix) if fix and built_hash else None
            state.failed_intent = list(res.intent_problems) \
                if state.failed and self._intent_only(res) else None
        if fix and not preview:
            self._turn_failed = True
            return fix
        return None

    @staticmethod
    def child_verdicts(res):
        """The Atech verdicts the sandbox child computed (R121/R123), or
        None when the Result carries none. The child marks a Result it
        checked with `atech_checked = True` (its verdicts may then be {}:
        no module to check); a non-empty `atech_verdicts` on a Result the
        panel has not checked can only have come from the child as well."""
        verdicts = getattr(res, "atech_verdicts", None)
        if getattr(res, "atech_checked", False):
            return verdicts if isinstance(verdicts, dict) else {}
        if isinstance(verdicts, dict) and verdicts:
            return verdicts
        return None

    @staticmethod
    def _atech_check(res):
        """The Atech port verdicts of the final build (R94), off the GUI
        thread where possible (R123): the child's verdicts when the Result
        carries them, build.atech_check (ap.check on this thread) only as a
        fallback. Never raises: a check that cannot run is a note, not a
        failed build."""
        child = AgentPanel.child_verdicts(res)
        if child is not None:
            _log("atech verdicts from the build child (%d module(s)); "
                 "GUI-thread check skipped" % len(child))
            return child
        fn = getattr(build, "atech_check", None)
        if not callable(fn):
            return {}
        try:
            return fn(res) or {}
        except Exception as exc:                       # noqa: BLE001
            _log("atech_check: %r" % (exc,))
            return {}

    @staticmethod
    def _start(state, files, preview):
        """build.start (R93): returns a PendingBuild, or None when there is
        nothing to build. Imports and in-process builds come back already
        finished; a sandboxed build is polled."""
        return build.start(state.ws, files, state.prev, preview=preview)

    @staticmethod
    def _intent_only(res):
        """True when the only measured problems of `res` are misses against
        intent.json (S49)."""
        if not getattr(res, "intent_problems", None):
            return False
        rest = copy.copy(res)
        rest.intent_problems = []
        try:
            return not build.failures(rest)
        except Exception as exc:                       # noqa: BLE001
            _log("intent_only: %r" % (exc,))
            return False

    def _caps_undeclared(self, res):
        """S51: True when the Atech verdicts of `res` fail on slide_path
        only, while the workspace's intent.json does not declare
        "fitted_after" yet and the build made a part that can be the cap.

        The agent writes model.py (a closed case with its end caps) before
        intent.json, so the first preview checks the modules' slide paths
        with the caps in place and fails them: red "check failed" for
        36-129 s of every Atech first preview (eval r6). That is the draft
        not yet saying which parts go on after the modules. A declared
        fitted_after (even []) that still fails is a real failure, as is any
        other Atech FAIL. Previews only: the end of the turn settles the
        same result as the final build (_finish_turn), where slide_path
        still fails the turn."""
        fails = [k for checks in (getattr(res, "atech_verdicts", None)
                                  or {}).values()
                 for k, v in checks.items() if v == "FAIL"]
        if not fails or any(k != "slide_path" for k in fails):
            return False
        # Only when ./check really honours "fitted_after": otherwise the
        # prompt tells the agent to leave the slide paths open (SLIDE_OPEN)
        # and a closed one is a real failure, not an undeclared cap.
        try:
            if not build.kit_reads_fitted_after():
                return False
        except Exception as exc:                       # noqa: BLE001
            _log("caps undeclared: %r" % (exc,))
            return False
        # The workspace the build read (the result's own), not whichever
        # turn is current when the preview settles.
        ws = getattr(res, "workspace", None) or getattr(self, "_ws", None)
        if self._declares_fitted_after(ws):
            return False
        for m in res.measurements:
            o = FreeCAD_doc_obj(res.doc, m.get("name"))
            if getattr(o, "AtechRole", None) is None:
                return True             # a part of the design: a cap can be
        return False

    @staticmethod
    def _declares_fitted_after(ws):
        """True when <ws>/intent.json has a "fitted_after" key; also True
        when it cannot be read (unknown: not treated as undeclared)."""
        if not ws:
            return False
        path = os.path.join(ws, build.INTENT)
        if not os.path.lexists(path):
            return False
        try:
            if os.path.islink(path):
                return True
            with open(path, encoding="utf-8-sig") as fh:
                intent = json.load(fh)
        except (OSError, ValueError):
            return True
        return not isinstance(intent, dict) or build.FITTED_AFTER in intent

    #: R174: the card line (fits the mono body at the default sidebar
    #: width) and the wrapped note that explains it.
    SLIDE_PROGRESS_LINE = "in progress: not yet declared as fitted after"
    SLIDE_PROGRESS_NOTE = (
        "A module's slide path is closed by a part not yet declared as "
        "fitted after the modules (intent.json \"fitted_after\"). The "
        "end-of-turn check still fails it if it stays that way.")

    def _in_progress(self, res):
        """S49 + S51: the card lines saying why a preview whose only
        problems are work in progress is not a failed check, or None when
        something else is wrong."""
        caps = self._caps_undeclared(res)
        if not getattr(res, "intent_problems", None) and not caps:
            return None
        rest = copy.copy(res)
        rest.intent_problems = []
        if caps:
            rest.atech_verdicts = {
                label: {k: v for k, v in checks.items() if k != "slide_path"}
                for label, checks in (res.atech_verdicts or {}).items()}
        try:
            if build.failures(rest):
                return None
        except Exception as exc:                       # noqa: BLE001
            _log("in progress: %r" % (exc,))
            return None
        lines = []
        if getattr(res, "intent_problems", None):
            lines.append("in progress: not at the intent.json targets yet")
        if caps:
            # R174: the mono body clips (no wrap): the 99-char sentence
            # showed only to "...is closed by" (318 px of a 655 px
            # sizeHint, GUI r7_19/r7_20). One short line here; the reason
            # goes in the card's wrapped note (_settle).
            lines.append(self.SLIDE_PROGRESS_LINE)
            self._progress_note = self.SLIDE_PROGRESS_NOTE
        return lines

    def _build_lines(self, res, preview):
        """(card lines, fix message or None, (status text, kind)).
        Sets self._progress_note: the card note of an in-progress preview
        (R174), "" otherwise."""
        self._progress_note = ""
        if preview:
            self._preview_intent = None
        if not res.ok:
            # One line on the card; the full traceback goes to the agent and
            # to the Report view (R26, R74).
            _log("build failed (%s):\n%s" % (res.source, res.error))
            lines = [_card_error(res.error)]
            if preview:
                # The agent is still working; it may fix this itself.
                self.stats["previews_failed"] += 1
                self._preview_error = res.error
                return lines, None, ("preview failed", "idle")
            return lines, self._fix_message(res.error), ("failed", "fail")
        self._preview_error = ""
        lines = []
        if res.kept:
            lines.append("kept previous: %s (your features use it)"
                         % ", ".join(res.kept))
        for m in res.measurements:
            try:
                vol = "{:,.1f}".format(float(m["volume_mm3"])).replace(",", " ")
            except (TypeError, ValueError):
                vol = "—"
            bb = m.get("bbox_bound") or []
            dims = " x ".join("%g" % v for v in bb) if len(bb) == 3 else "—"
            o = FreeCAD_doc_obj(res.doc, m.get("name"))
            if o is not None and getattr(o, "AtechPorts", None):
                lines.append("%-18s seated on port%s %s" % (
                    (m.get("label") or "?")[:18],
                    "s" if len(o.AtechPorts) > 1 else "",
                    ", ".join(str(x) for x in sorted(o.AtechPorts))))
                continue
            if o is not None and getattr(o, "AtechRole", None) == "board":
                lines.append("%-18s Atech 14-port board"
                             % (m.get("label") or "?")[:18])
                continue
            n = m.get("solids")
            lines.append("%-18s %10s mm³  %s%s" % (
                (m.get("label") or "?")[:18], vol, dims,
                "  (%s solids)" % n if n and n > 1 else ""))
        bad = build.failures(res)
        progress = self._in_progress(res) if bad and preview else None
        if progress:
            # S49: the prompt has the agent write intent.json with the
            # FINAL targets right after its first draft, so a correct draft
            # still short of them is work in progress, not a failed check
            # (8/42 previews in eval round 5 showed "check failed" for
            # this alone). S51: likewise a closed Atech case whose caps are
            # not declared fitted_after yet. Nothing goes back to the agent
            # from here: the end of the turn settles this result as the
            # final build and enforces both then (_finish_turn).
            self._preview_intent = res
            lines.extend(progress)
            return lines, None, ("preview: in progress", "idle")
        if bad and preview:
            self.stats["previews_failed"] += 1
            self._preview_error = ("Atech Atelier built it, but the measurement "
                                   "check failed: %s." % bad)
            return lines, None, ("preview: check failed", "idle")
        if bad:
            return lines, ("Atech Atelier built it, but the measurement check "
                           "failed: %s. Each body must be one valid solid."
                           % bad), ("check failed", "fail")
        return lines, None, ("%d built" % len(res.created), "ok")

    @staticmethod
    def _viewport():
        """acadagent.viewport, or None where it cannot load (no GUI)."""
        try:
            from . import viewport
            return viewport
        except Exception as exc:                       # noqa: BLE001
            _log("viewport: %r" % (exc,))
            return None

    @staticmethod
    def _built_objects(res):
        """The document objects this build created (by Name)."""
        try:
            import FreeCAD
            doc = FreeCAD.getDocument(res.doc)
        except Exception:                              # noqa: BLE001
            return None, []
        objs = []
        for n in res.created or ():
            try:
                o = doc.getObject(n)
            except Exception:                          # noqa: BLE001
                o = None
            if o is not None:
                objs.append(o)
        return doc, objs

    def _frame(self, state, res=None, preview=False):
        """Mesh quality and camera for a build that landed (R94, S23/S05).

        Coarse tessellation for a live preview, fine for the end-of-turn
        build (viewport.set_mesh_quality). The camera moves only when it has
        to (viewport.frame_if_needed): the chat's first build turns to the
        Atech module face when there is one (R82), isometric otherwise;
        later builds keep the user's view unless the model left it."""
        first = not state.framed
        state.framed = True
        vp = self._viewport()
        if vp is None:
            return
        doc, objs = self._built_objects(res) if res is not None \
            else (None, [])
        if objs:
            try:
                vp.set_mesh_quality(objs, final=not preview)
            except Exception as exc:                   # noqa: BLE001
                _log("mesh quality: %r" % (exc,))

        def _now():
            turn = first
            if not getattr(state, "faced", False):
                # D50 (R94): an Atech chat's first build is often a
                # placeholder with no board yet, framed isometric; the board
                # and modules that land later were then kept in that view -
                # the product seen from the back. The first build that HAS a
                # module face turns to it, once per chat.
                face = None
                fn = getattr(vp, "module_face_direction", None)
                try:
                    face = fn(doc) if callable(fn) and doc is not None \
                        else None
                except Exception as exc:               # noqa: BLE001
                    _log("module face: %r" % (exc,))
                if face is not None:
                    turn = True
                    state.faced = True
            try:
                vp.frame_if_needed(objs, first=turn, doc=doc)
            except Exception as exc:                   # noqa: BLE001
                _log("frame: %r" % (exc,))
        # After the event loop has shown the new objects: framing needs
        # their view providers' bounds.
        QtCore.QTimer.singleShot(0, _now)

    def _send_fix(self, message):
        """Hand a build failure back to the agent - bounded, and visible.
        The fix turn stays on the chat (document) that failed."""
        self._attempt = getattr(self, "_attempt", 0) + 1
        if self._attempt > self.MAX_FIX_ATTEMPTS:
            self.show_notice(
                "The build still fails",
                "Tried %d fixes. The last error is in the build card above; "
                "describe the change differently or simplify it."
                % self.MAX_FIX_ATTEMPTS)
            return
        if self._doc_was_closed(self._cur):
            self._on_doc_closed_mid_turn(self._cur)
            return
        self._flash_hint("Sending the error back to the agent (fix %d of %d)…"
                         % (self._attempt, self.MAX_FIX_ATTEMPTS))
        self._send_claude(message + "\nFix model.py and write it again.",
                          state=self._cur, fix=True)

    def _on_claude_failed(self, msg):
        """Name the cause in words (R21): signed out, offline, or something
        else - raw CLI text only behind Details and in the Report view."""
        from . import claude_cli
        _log("claude failed: %s" % msg)
        self._stop_elapsed()
        kind = claude_cli.classify_failure(msg)
        budget = kind == getattr(claude_cli, "BUDGET", None)
        if self._card:
            self._card.set_status(
                "stopped" if kind == claude_cli.CANCELLED else
                ("budget limit" if budget else "failed"),
                "idle" if kind == claude_cli.CANCELLED else "fail")
            self._card = None
        self._busy = False
        self._finishing = False
        self._set_sending(False)
        if budget:
            self._on_budget_stop(msg)
            return
        self._restore_input()
        if kind == claude_cli.CANCELLED:
            self.set_backend_state("idle")
            return
        ok, _why = engine.available(engine.CLAUDE)
        if kind == claude_cli.AUTH:
            self._unavailable_kind = "auth"
            self.set_backend_state("offline")
            self._clear_empty()
            self._has_messages = True
            # Tracked as the offline notice, so the next turn replaces it
            # instead of stacking one sign-in notice per failed send.
            self._offline = self._add(self._auth_notice(self._retry_last))
            return
        if not ok:
            self._unavailable_kind = "missing"
            self.set_backend_state("offline")
            self._clear_empty()
            self._offline = self._offline_notice()
            return
        self.set_backend_state("idle")
        if kind == claude_cli.OFFLINE:
            self.show_notice(
                "No internet connection",
                "Claude Code could not reach Anthropic. Check the connection, "
                "then press Retry. Your message is back in the box below.",
                actions=[("Retry", self._retry_last)],
                detail=msg if len(msg) < 2000 else msg[-2000:])
            return
        self.show_notice(
            "The agent stopped before finishing",
            "Something went wrong while the agent was working. Your message "
            "is back in the box below; press Retry to send it again.",
            actions=[("Retry", self._retry_last)],
            detail=msg if len(msg) < 2000 else msg[-2000:])

    # ------------------------------------------------ budget stop (R101)
    def _budget_of(self, msg):
        """The limit the turn ran under: what it was started with, else
        the "$3" in the CLI's message, else None (never a guess)."""
        b = getattr(self, "_turn_budget", None)
        if b:
            return b
        import re
        m = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", msg or "")
        return float(m.group(1)) if m else None

    def _on_budget_stop(self, msg):
        """The turn hit --max-budget-usd: say so plainly, offer Continue,
        and keep what the agent got to (R101, dogfood D45/D46)."""
        self.set_backend_state("idle")
        b = self._budget_of(msg)
        limit = self._money(b) if b else "budget"
        kept = self._keep_last_preview()
        body = ("Stopped at the %s limit for one message — Settings > "
                "Budget per reply. " % limit)
        body += ("The last preview that built stays in the document. "
                 if kept else "Nothing had built yet. ")
        body += "Continue lets the agent pick up where it stopped%s." % (
            " with another %s" % limit if b else "")
        self._budget_notice = self.show_notice(
            "Stopped at the %s limit" % limit if b else
            "Stopped at the budget limit", body,
            actions=[("Continue",
                      functools.partial(self._continue_turn, self._cur)),
                     ("Settings…", self._on_settings)],
            detail=msg if len(msg) < 2000 else msg[-2000:])

    def _keep_last_preview(self):
        """R101: when a turn stops early, what the agent wrote last is
        still worth seeing. A build in flight is left to finish; a newer
        model.py that compiles and was never built is built as a preview
        (no fix turn). A failed build changes nothing, so the last preview
        that built stays either way. True when a preview built (or is
        building) this turn."""
        if self._pending is not None:
            # A newer script may land while this build runs; the live
            # preview path is closed now the turn is over, so look again
            # when it ends.
            if self._after_build is None:
                self._after_build = self._keep_last_preview
            self._preview_again = False
            return True
        if self._cur is not None and self._ws and os.path.isdir(self._ws):
            try:
                files = self._preview_files()
            except Exception as exc:                   # noqa: BLE001
                _log("keep preview: %r" % (exc,))
                files = []
            if files:
                self._applied = build.snapshot(self._ws)
                self._run_build(files, preview=True)
        return self._pending is not None or \
            getattr(self, "_last_preview_ok", None) is not None

    def _continue_turn(self, state=None):
        """"Continue" on a budget notice: one more turn on the same chat
        and session, with a fresh budget. R190: the notice carries its own
        chat, which is not the current one after a document switch."""
        n = getattr(self, "_budget_notice", None)
        if n is not None:
            for btn in getattr(n, "buttons", []):
                btn.setEnabled(False)
        if self._busy:
            self._flash_hint(
                "Still working on the previous message. Press stop to interrupt.")
            return
        state = state if state is not None else self._cur
        self._attempt = 0
        self.say("Continue", role="user")
        self._send_claude(
            "Continue where you stopped: you hit the budget limit for one "
            "message. Finish the design in model.py; keep the checks short.",
            state=state)

    def _on_chunk(self, text):
        if self._card:
            self._card.set_status("replied", "ok")
        self.say(text)

    def _on_tool(self, info):
        c = ToolCard(info.get("name", "tool"),
                     str(info.get("input", ""))[:70])
        self._add(c)
        out = str(info.get("output", ""))[:2000]
        if out:
            c.append(out)
        c.set_status(info.get("status") or "done", "ok")

    def _on_reply(self, _text):
        # This literal must track ToolCard's default status or the done-state
        # silently stops applying.
        if self._card and self._card.status.text() == "working":
            self._card.set_status("done", "ok")
        self._busy = False
        self._set_sending(False)
        self.set_backend_state("idle")

    def _on_chat_failed(self, msg):
        _log("chat failed: %s" % msg)
        # R24: after Stop, whatever the worker reports next (a dropped
        # connection, a late error) is the cancellation, not "offline".
        cancelled = msg == "cancelled" or self._stopped
        if self._card:
            self._card.set_status("stopped" if cancelled else "failed",
                                  "idle" if cancelled else "fail")
            self._card = None
        self._busy = False
        self._set_sending(False)
        self._restore_input()
        if cancelled:
            self.set_backend_state("idle")
            return
        self.set_backend_state("offline")
        base = self._base_url()
        self.show_notice(
            "The agent stopped before replying",
            "The connection to %s dropped mid-request. Your message is back "
            "in the box below; press Retry to send it again."
            % _hostport(base),
            actions=[("Retry", self._retry_last)],
            detail=msg if len(msg) < 2000 else msg[-2000:])

    def _on_build(self):
        """Measure every solid in the active document. Main thread only."""
        from . import runner
        doc = self._active_document()
        self.refresh_doc_pill()
        if doc is None:
            self.show_notice(
                "No document open",
                "The agent measures what is on screen. Open a file, or start "
                "an empty document and describe what you want built.",
                actions=self._nodoc_actions())
            return
        card = ToolCard("Measure", doc.Label)
        self._clear_empty()
        self._add(card)
        rows = [runner.measure(o) for o in doc.Objects]
        rows = [r for r in rows if r.get("volume_mm3") is not None]
        if not rows:
            # Nothing failed. An empty document is a state, not an error.
            card.append("This document has no solid-bearing objects yet.")
            card.set_status("nothing to measure", "idle")
            return
        for r in rows:
            try:
                vol = "{:,.1f}".format(float(r["volume_mm3"])).replace(",", " ")
            except (TypeError, ValueError):
                vol = "—"
            card.append("%-17s %11s mm³  %s%s" % (
                (r["label"] or r["name"] or "?")[:17], vol,
                "" if r["solids"] == 1 else "%s solids" % r["solids"],
                "" if r["valid"] else "  INVALID"))
        bad = [r for r in rows if r["solids"] != 1 or not r["valid"]]
        if bad:
            card.append("")
            card.append("%d object(s) not a single valid solid" % len(bad))
            card.set_status("check failed", "fail")
        else:
            card.set_status("%d measured" % len(rows), "ok")

    def _on_settings(self):
        """After Save, re-check the engine so the chat reflects the change
        (a new engine, a Claude Code path) without a restart (R28)."""
        from . import settings
        if settings.open_dialog(self, keep_workspaces=self.workspaces()):
            self._probe_backend_again()


# ------------------------------------------------------------------ mount
def ensure_panel():
    """Mount the shell if absent, show the Chat page, return the AgentPanel."""
    from . import shell
    return shell.show_chat()


def get_panel():
    from . import shell
    return shell.chat_panel()
