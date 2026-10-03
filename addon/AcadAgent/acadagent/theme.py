"""theme — panel styling.

Scoped to the dock so FreeCAD's own dialogs stay legible, and so this can
never fight the token system in branding/assets/theme/Atech Atelier Dark.yaml.
App chrome lives in that YAML; panel chrome lives here. They do not merge.

PALETTE — Atech, cool blue-grey. The previous values came from
docs/prd/assets/agent_workbench_mockup.html and were WARM (ink hue 43deg,
muted 40deg) sitting beside cool chrome (bg hue 232deg), which is why the
dock read as a yellowed panel bolted onto a blue-black app.

    bg      #0F1017   flush with PrimaryColor - the transcript is the window
    raised  #191C27   cards lift off the transcript; they carry the content
    bubble  #1E2230
    border  #262A38
    ink     #E9EBF3
    muted   #9BA4BE
    dim     #6E7590   (AA on #191C27)
    brand   #5AA2FF -> #9A6BFF   the one gradient, on the one primary action
    ok      #5FB98C   (matches the YAML's SketcherFullyConstrainedColor)
    fail    #E0705F   reserved for genuine failures so red keeps its meaning

Mint #6FD3B8 is retired: it appears nowhere in the Atech brand.
"""

PANEL_QSS = """
#PanelHead { background: #191C27; border-bottom: 1px solid #262A38; }
#PanelTitle { color: #6E7590; font-size: 11px; font-weight: 600; letter-spacing: 1px; }

#PillOk, #PillIdle, #PillRun, #PillFail {
    font-family: monospace; font-size: 11px; padding: 2px 8px;
    border: 1px solid #262A38; border-radius: 8px; color: #9BA4BE;
}
#PillRun  { color: #5FB98C; border-color: #5FB98C; }
#PillFail { color: #E0705F; border-color: #E0705F; }

/* The dock must READ as a surface, not as a hole in the viewport.
   Measured on 04_team.png: with #Stream flush at #0F1017, every pixel from
   x=0..1606 at y=600 and y=700 was #0F1017 — for ~300px of span the panel and
   the 3D viewport were literally the same colour with nothing between them, so
   the panel only appeared to exist where a card happened to sit. One step up
   (#131620) plus a right edge gives the dock a boundary the eye can find. */
#AgentPanel { background: #131620; border-right: 1px solid #2E3142; }

#Stream { background: #131620; border: none; }
#StreamInner { background: #131620; }
#Stream > QWidget > QWidget { background: #131620; }

#Stream QScrollBar:vertical { background: transparent; width: 9px; margin: 0; }
#Stream QScrollBar:horizontal { background: transparent; height: 9px; margin: 0; }
#Stream QScrollBar::handle { background: #262A38; border-radius: 4px;
    min-height: 28px; min-width: 28px; }
#Stream QScrollBar::handle:hover { background: #3A4055; }
#Stream QScrollBar::add-line, #Stream QScrollBar::sub-line { height: 0; width: 0; }
#Stream QScrollBar::add-page, #Stream QScrollBar::sub-page { background: transparent; }

#UserBubble {
    background: #1E2230; border: 1px solid #262A38; border-radius: 6px;
    padding: 8px 10px; color: #E9EBF3;
}
#AgentText { color: #E9EBF3; font-size: 12px; }

#ToolCard { background: #191C27; border: 1px solid #262A38; border-radius: 6px; }
#ToolCardHead { background: #191C27; border-bottom: 1px solid #262A38; }
#ToolName { color: #E9EBF3; font-family: monospace; font-size: 11px; font-weight: 600; }
#ToolArgs { color: #9BA4BE; font-family: monospace; font-size: 11px; }
/* monospace ONLY where character alignment is load-bearing */
#ToolBody { color: #9BA4BE; font-family: monospace; font-size: 11px; }
/* prose wraps, in the UI font */
#ToolProse { color: #9BA4BE; font-size: 12px; }
#ShotCap { color: #6E7590; font-family: monospace; font-size: 11px;
    border-top: 1px solid #262A38; }

#StatusRun  { color: #5FB98C; font-size: 11px; font-weight: 600; }
#StatusOk   { color: #5FB98C; font-size: 11px; font-weight: 600; }
#StatusFail { color: #E0705F; font-size: 11px; font-weight: 600; }
#StatusIdle { color: #6E7590; font-size: 11px; font-weight: 600; }

/* --- designed system states. Never a traceback. --- */
#NoticeWarn { background: #191C27; border: 1px solid #262A38;
    border-left: 2px solid #5AA2FF; border-radius: 6px; }
#NoticeTitle { color: #E9EBF3; font-size: 13px; font-weight: 600; }
#NoticeBody { color: #9BA4BE; font-size: 12px; }
#ErrDetail { color: #6E7590; font-family: monospace; font-size: 10px; }
#NoticeBtn {
    background: transparent; color: #9BA4BE; border: 1px solid #2E3142;
    border-radius: 5px; padding: 5px 10px; font-size: 12px;
}
#NoticeBtn:hover { color: #E9EBF3; border-color: #3A4055; background: #1E2230; }

#EmptyStateBox { background: transparent; }
#EmptyStateTitle { color: #E9EBF3; font-size: 13px; font-weight: 600; }
#EmptyState { color: #9BA4BE; font-size: 12px; }
#PromptRow {
    color: #9BA4BE; font-size: 12px; padding: 6px 9px;
    background: #14161F; border: 1px solid #262A38; border-radius: 5px;
}
#PromptRow:hover { color: #E9EBF3; border-color: #5AA2FF; background: #1E2230; }

#Composer { background: #0F1017; border-top: 1px solid #262A38; }
#ComposerHint { color: #E0B052; font-size: 11px; }
#Composer QLineEdit {
    background: #0B0C12; border: 1px solid #262A38; border-radius: 5px;
    min-width: 190px; min-height: 28px; padding: 6px 10px; color: #E9EBF3;
}
#Composer QLineEdit:focus { border-color: #5AA2FF; }

/* Secondary controls are outlines, so SendBtn is the only filled control. */
#Composer QPushButton {
    background: transparent; color: #9BA4BE; border: 1px solid #262A38;
    border-radius: 5px; padding: 5px 11px;
}
#Composer QPushButton:hover { color: #E9EBF3; border-color: #3A4055; }
#Composer QPushButton:disabled { color: #5A6078; border-color: #262A38; }

/* The primary action is the most brand-saturated pixel in the app.
   MEASURED: written as a bare '#SendBtn' these rules did not apply at all -
   the button rendered #0F1017 on a #262A38 outline. Qt resolves QSS by CSS2
   specificity, and '#Composer QPushButton' is a two-part selector that
   outranks a one-part id, however far down the file it sits. Scoping Send and
   Stop under #Composer matches that specificity so source order decides. */
#Composer QPushButton#SendBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #5AA2FF, stop:1 #9A6BFF);
    color: #0F1017; border: none; border-radius: 5px;
    padding: 6px 14px; font-weight: 600;
}
#Composer QPushButton#SendBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6FADFF, stop:1 #A87EFF);
    color: #0F1017; border: none;
}
#Composer QPushButton#StopBtn {
    background: transparent; color: #E0705F; border: 1px solid #E0705F;
    border-radius: 5px; padding: 6px 14px; font-weight: 600;
}
#Composer QPushButton#StopBtn:hover { background: #1E2230; color: #E0705F;
    border-color: #E0705F; }
"""


def apply_panel_theme(widget):
    widget.setStyleSheet(PANEL_QSS)


# --- terminal -------------------------------------------------------------
# Same palette as the panel above and as branding/assets/theme/, so the shell
# does not read as a foreign window pasted into the dock.
TERMINAL_QSS = """
#TermOut {
    background: #0B0C12; color: #C9CEDE;
    border: none; border-bottom: 1px solid #262A38;
    selection-background-color: #1E2230;
}
#TermRow { background: #14161F; }
#TermInput {
    background: #0F1017; color: #E9EBF3;
    border: 1px solid #2E3142; border-radius: 5px; padding: 5px 8px;
}
#TermInput:focus { border-color: #5AA2FF; }
#TermBtn {
    background: #1E2230; color: #C9CEDE;
    border: 1px solid #2E3142; border-radius: 5px; padding: 5px 11px;
}
#TermBtn:hover { background: #262A38; border-color: #3A4055; }
"""
