# Usability audit: 100 standard desktop-app issues

Atech AI CAD (formerly Atech Atelier) was checked against 100 common
desktop-app usability problems.

- **Round 1:** 2026-10-26, on the `macos-support` branch.
- **Round 2:** 2026-10-26, on `main` at 982befb (macOS app and installer,
  Studio-style sidebar and project picker, 3D board look, design levels,
  module and firmware plans).

Every item was checked again against the current code. Round 2 also lists
29 new issues that came with the new code. Paths are under
`addon/AcadAgent/acadagent/` unless they say otherwise; line numbers are
for 982befb.

**OK** = done · **PARTIAL** = some of it is done · **MISSING** = not done.
The **Δ** column shows the change since round 1: **↑** better, **↓** worse,
blank = no change.

| | OK | PARTIAL | MISSING |
|---|---|---|---|
| Round 1 | 25 | 60 | 15 |
| Round 2 | 22 | 64 | 14 |

- **Better (10):** #12, 42, 49, 51, 55, 62, 64, 66, 82, 95.
- **Worse (6):** #24, 48, 58, 83, 91, 92.
- **Still open from round 1's "Do these first":** all 10.

## Do these first (round 2)

The design levels changed the priorities: items 1–4 below can waste a
user's whole evening or their money.

1. **A usage limit runs through the remaining design levels (N22, #99).**
   `classify_failure` has no usage-limit, 429 or overloaded class, so these
   errors count as generic failures. A generic failure on a design level
   rolls back and moves on to the next level (`panel.py:6134`), which fails
   the same way. Each level prints "Level N did not pass", and the limit is
   never named. Add LIMIT and OVERLOADED classes that stop the ladder,
   leave it resumable and show the reset time.
2. **Retry and Continue end the design levels without saying so (N24).**
   After level 1, `model.py` exists, so `start_levels` treats any message
   that isn't a level message as the user taking over and clears the ladder
   (`build.py:511`). Retry (`panel.py:4756`) resends the user's original
   request against the half-built model; Continue resends "Continue where
   you stopped…". Both should resend the level message while a ladder is
   running.
3. **One message can cost far more than "Budget per reply" suggests (N23).**
   Each of the 9 levels, and each of their up to 5 fix turns, is a separate
   reply with a fresh $25 quality budget. Add a budget for the whole
   request, a running total, and the level count in the mode tooltip.
4. **Ports 8 and 12 are reserved, but the examples use them (N29).** The
   Atech SDK catalog (`agent_kit/atech_sdk_catalog.json`, 14port) marks
   ports 8 and 12 as reserved, so `./check` warns "the firmware cannot drive
   a module there". Yet the product reference teaches "a nose sensor ahead
   of FLAT port 8", and 8 of the 10 seeds use port 8 or the pair 11+12
   (toy car, tank, lamp, handheld, clock, robot, speaker, weather station).
   Every forked seed starts with firmware warnings, and the agent gets
   conflicting instructions. Re-route the seeds onto free ports (1–7, 9–11,
   13, 14) and update `ATECH_PRODUCTS.md`, or fix the catalog if it's wrong.
5. **Sending a project to the Trash loses unsaved work (N6).**
   `trash_project` (`projects_store.py:1422`) closes the document without
   saving or asking, and deletes its chat folder for good. Ask or save
   first, and send chats to the Trash too.
6. **Environment variables silently override settings (#83).**
   `ATECH_PROMPT_MODE`, `ATECH_HARDWARE_MODE` and `ATECH_PROJECTS_DIR`
   overrule visible controls. Saving Settings even writes the environment
   variable's value over the user's choice (`settings.py:817`). Say "Set by
   $X", disable the control it overrides, and never save its value.
7. **Finish the rename (#19, #58, N1).** There are now two `PRODUCT`
   constants that disagree (`__init__.py:6` says Atelier, `style.py:49`
   says AI CAD). The README promises `AtechAICAD-*` downloads and
   `…/Atech AI CAD/` folders that the build doesn't produce. Rename
   `branding.xml`, `release_meta`, `macos_bundle`, `build_macos`, the data
   migration and the README in one change, plus a CI grep.
8. **The board look holds 157 MB and loads at startup (N16–N18, #48).**
   `board_look.prepare()` keeps every vertex as a Python list for the whole
   session, and `install()` builds every scene, including `measure_board()`,
   synchronously at startup. Cache numpy arrays, share nodes within a
   document, precompute normals, and load on a worker.
9. **Errors still unclear or wrong:** the offline pill says "Agent ready"
   (#85, `panel.py:6163`). "Open file…" can't open STEP or STL (#38,
   `panel.py:2711`). "The build still fails" has no buttons (#25).
10. **Help, About and Report a problem (#13, #16, #17, #20).** Still
    nothing in the app beyond Credits; `__version__` still says 0.1.0.

## A. Install, first run, onboarding

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 1 | Needs the terminal to install | PARTIAL | | The DMG is built (`branding/build_macos.sh:646`); notarization still prints SKIPPED, and CI only warns (`release.yml:189`). → Fail the release when it isn't notarized; make the DMG the main path. |
| 2 | Gatekeeper warnings | PARTIAL | | Covered only in the README (`README.md:303`). → Add "Open Anyway" steps to the release notes; refuse macOS assets that aren't notarized. |
| 3 | Claude Code missing | PARTIAL | | `install.sh:367` now offers to install it, but in the app the notice still has only Retry and Settings (`panel.py:2467`). → Add an "Install Claude Code" action that runs `INSTALL_COMMAND` in Terminal, then check again. |
| 4 | First-run tour | PARTIAL | | Welcome card and orbit hint only. The new sidebar adds two pill switches that look alike. → 3 steps: project picker, "What the agent builds" switch, chat box. |
| 5 | Empty states | OK | | |
| 6 | Signed out of Claude | PARTIAL | | "Open terminal" still starts bare `claude` (`panel.py:2540`). → Run `claude auth login` and check `auth_status()` until it passes. |
| 7 | Examples are easy to find | OK | | |
| 8 | Too much FreeCAD chrome | PARTIAL | | The full FreeCAD menu bar is still shown. |
| 9 | Opens on the right page | OK | | |
| 10 | Startup feedback | OK | | The dark splash is still shipped but never used. |
| 11 | No update check | MISSING | | → Check the latest GitHub release daily; the Update button can run `install.sh`. |
| 12 | No "What's new" | PARTIAL | ↑ | CHANGELOG.md exists and the release notes link to it; not in the app. → Ship it and show the new section once. |
| 13 | Version not visible | MISSING | | `__version__` is 0.1.0 and VERSION is 0.1.1; Finder's Get Info now shows the version. → Set `__version__` at build time; add About. |
| 14 | Uninstall leaves data behind | PARTIAL | | On Linux `install.sh:352` prints a literal "`<app name>`" placeholder; `~/.config/acadagent` and the projects folder aren't mentioned. → `--purge`, with the real paths. |
| 15 | Data migration between names | PARTIAL (risk) | | Still handles "Atech Studio" only; the README already promises Atelier → AI CAD. |
| 16 | No bug report from the app | MISSING | | |
| 17 | Logs hard to find | PARTIAL | | Report view only. |
| 18 | No setup check | PARTIAL | | → Reuse the `install.sh` checks in a "Check setup" dialog. |
| 19 | Mixed product name | PARTIAL | | The gap is wider; see N1. |
| 20 | No help in the app | MISSING | | |

## C. Errors, messages, recovery

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 21 | Raw tracebacks | OK | | The new export status shows a raw exception (`export_tools.py:1775`). |
| 22 | Errors without a next step | PARTIAL | | About 42 messages end with "The details are in the Report view." |
| 23 | Network and API errors | PARTIAL | | A BUDGET class was added; usage limit, 429, overloaded and 5xx are still generic. See "Do these first" #1. |
| 24 | Errors swallowed silently | PARTIAL | ↓ | 127 `except: pass` blocks (was 109). `shell._notify` returns silently when there's no panel. |
| 25 | Failed build gives no options | PARTIAL | | `panel.py:6000`. |
| 26 | Hung processes | OK | | |
| 27 | Error popups block the app | OK | | The picker's rename, duplicate and export errors are still modal (`navbar.py:347`). |
| 28 | Errors can't be copied | PARTIAL | | |
| 29 | Jargon | PARTIAL | | "sandbox-exec", "bwrap", "Report view", ".FCStd". |
| 30 | Claude Code crash mid-turn | OK | | Still no test that kills the process mid-turn. |

## D. Keeping your work safe

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 31 | Autosave | OK | | |
| 32 | Crash recovery | OK | | |
| 33 | Undo agent changes | OK | | |
| 34 | History of builds | OK | | Past chats menu added. |
| 35 | Unsaved changes on quit | OK | | |
| 36 | Deleting safely | PARTIAL | | Projects go to the Trash, but their chats are deleted for good; see N6. |
| 37 | Export defaults | PARTIAL | | Every dialog still starts on ~/Desktop. |
| 38 | Opening files | PARTIAL (bug) | | Not fixed: `panel.py:2711` has no STL/3MF and uses `openDocument` on STEP. → Use `shell.open_path`. |
| 39 | Where data lives | PARTIAL | | |
| 40 | Disk use grows | PARTIAL (bug) | | Not fixed: `_park_chat` is now `_archive_chat` (`panel.py:4318`), and still drops past chats without deleting their folders. |

## E. Speed and responsiveness

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 41 | Work on the GUI thread | PARTIAL | | Export, share sheet, autosave during a turn; now also the board look (N18). |
| 42 | Progress for long tasks | PARTIAL | ↑ | Examples build through the chat with a card, but it doesn't count up. → Call `_start_elapsed` from `_run_build`. |
| 43 | Cancel | PARTIAL | | Example builds set `_pending` without `_busy`, so no Stop button appears. → Base Stop on `_busy or _pending`. |
| 44 | Streaming | OK | | |
| 45 | Large models | OK | | |
| 46 | Memory over long sessions | PARTIAL | | Plus 157 MB in the board look (N16). |
| 47 | Minimised or in the background | PARTIAL | | |
| 48 | Addon startup cost | PARTIAL | ↓ | `InitGui.py:59` → `board_look.install()` builds every scene and `measure_board()` at startup. |
| 49 | Timers while idle | PARTIAL | ↑ | The picker follows document events; the 800 ms and 3 s ticks remain, and the board look polls every 250 ms while a dialog is open. |
| 50 | Several requests at once | PARTIAL | | |

## F. Finding things, navigation, help

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 51 | Keyboard shortcuts | PARTIAL | ↑ | Nine new keys and a shortcut sheet; still no New chat, Esc to stop, or Export. |
| 52 | Command palette | MISSING | | |
| 53 | Tooltips | OK | | |
| 54 | Menu bar | PARTIAL | | `EXPORT_COMMANDS` only appear in the right-click menu. |
| 55 | Right-click menus | PARTIAL | ↑ | The 3D view, tree and Home cards have them; chat messages don't. |
| 56 | Where am I | OK | | No project name in the window title. |
| 57 | What can I ask | PARTIAL | | |
| 58 | Consistent wording | PARTIAL | ↓ | Two `PRODUCT` constants; menu text in Title Case vs sentence case. |
| 59 | Back to Home | MISSING | | |
| 60 | Search | PARTIAL | | |

## G. Accessibility and display

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 61 | Hard-coded pixel sizes | PARTIAL | | 132 `font-size: NNpx`, plus 4 new `setPixelSize`. |
| 62 | Follows light/dark | OK | ↑ | Now falls back to `palette_is_dark()`; `apply_theme_choice` still does nothing when Linux reports "Unknown". |
| 63 | Contrast | PARTIAL | | `dim` is unchanged (2.5:1 / 3.0:1); the new pill labels are about 4.2:1. |
| 64 | Keyboard focus | PARTIAL | ↑ | New focus rings; the picker, Parts button and Send button still have none; no tab order. |
| 65 | Screen-reader names | PARTIAL | | |
| 66 | Small screens | PARTIAL | ↑ | The sidebar narrows; dialogs still aren't kept within the screen. |
| 67 | Text size | MISSING | | |
| 68 | Reduce motion | PARTIAL | | Plus a new 450 ms module slide (N27). |
| 69 | Translation and units | MISSING | | |
| 70 | Icons in both themes | OK | | `theme.py` is still dead code. |

## H. Fitting in with macOS and Linux

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 71 | Window layout remembered | PARTIAL | | |
| 72 | Several monitors | PARTIAL | | |
| 73 | macOS conventions | PARTIAL | | ⌘P is still Parts; ⌘, isn't Atech settings; the sheet lists Redo as Ctrl+Y. |
| 74 | File associations | OK | | |
| 75 | Drag and drop | PARTIAL | | A drop on the chat box still opens the file as a project. |
| 76 | Clipboard | PARTIAL | | |
| 77 | Notice when a turn ends | MISSING | | Matters more now that the design levels can run for an hour. |
| 78 | Only one copy running | PARTIAL | | |
| 79 | Sleep, wake, network changes | PARTIAL | | |
| 80 | Linux desktop | PARTIAL | | |

## I. Settings, privacy, network

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 81 | Settings layout | PARTIAL | | |
| 82 | When settings apply | PARTIAL | ↑ | Said only in the hardware switch's tooltip. |
| 83 | Settings only reachable by env var | MISSING | ↓ | About 20 variables, 8 of them new; 3 silently override controls (see "Do these first" #6); `ATECH_PROMPT_OFF` now has 40 switches. |
| 84 | Privacy notice | PARTIAL | | |
| 85 | Offline | PARTIAL (bug) | | Not fixed (`panel.py:6163`). |
| 86 | Proxy | MISSING | | |
| 87 | Units | MISSING | | |
| 88 | Model and cost | OK | | |
| 89 | Secrets | OK | | |
| 90 | What the agent can do | PARTIAL | | |

## J. The chat and the agent

| # | Issue | Status | Δ | Where it stands → fix |
|---|---|---|---|---|
| 91 | How long a turn takes | PARTIAL | ↓ | Was OK: a request is now up to 9 levels, each timed alone, with no overall clock or estimate. → A ladder progress line with total time and an estimate. |
| 92 | Changing course mid-turn | PARTIAL | ↓ | The levels follow each other automatically; the user's only way in is Stop. → Queue the message in place of the next level; add "Stop after this level". |
| 93 | Measured facts vs claims | PARTIAL | | |
| 94 | Retry, edit and resend | PARTIAL | | Retry is now harmful during the levels (N24). |
| 95 | Managing chats | PARTIAL | ↑ | A Past chats menu exists; no rename, delete or export. |
| 96 | Attach a reference picture | PARTIAL | | |
| 97 | Clarifying questions | MISSING (by design) | | |
| 98 | Show the code | PARTIAL | | |
| 99 | Usage limit | MISSING | | Now harmful (N22). |
| 100 | "This is wrong" feedback | PARTIAL | | |

## New issues in round 2

**Install and naming**

- **N1. The README promises files and folders that don't ship.** It
  promises `AtechAICAD-*` files, `…/Atech AI CAD/` data folders and "0.1.2
  under the new name"; the build makes `AtechAtelier-*` and VERSION is
  0.1.1. `install.sh:343` works out the data folder from the `.app` name.
  → One rename change; until then the README should describe what ships.
- **N2. The README points to UI that is gone or wrong.** The "Atech → New
  Project" menu was removed. "Show in Finder" also appears on Linux.
- **N3. A release published by hand has no macOS build.**
  `publish_release.sh` uploads only the AppImage, and `release.yml` skips
  existing releases. `install.sh` then quietly installs an older DMG.
- **N4. Two different FUSE instructions.** `install.sh` says fuse3, the
  README says libfuse2.
- **N5. Two switches that look alike, with "CAD + electronics" on by
  default.** A newcomer without Atech hardware gets the board in a "car".
  → Ask once on first run, and label the switch.

**Keeping work safe**

- **N6. Sending a project to the Trash loses unsaved work** and deletes its
  chats for good.
- **N7. Changing the projects folder makes projects disappear from Home.**
  → Offer to move them.
- **N8. Exports overwrite files without asking.** This covers part exports
  and the extension added after the dialog. A failed BOM write is silent.
- **N9. Rename and Duplicate silently save the open document**, including
  agent edits the user hasn't accepted.
- **N10. Starter projects are copied among the user's own projects**, with
  no label, and can't be restored.

**Settings and the agent**

- **N22. A usage limit runs through the remaining levels** with misleading
  messages ("Do these first" #1).
- **N23. The real cost of one request is hidden** ("Do these first" #3).
- **N24. Retry and Continue end the design levels without saying so**
  ("Do these first" #2).
- **N25. The design levels, module plan and firmware plan can't be seen or
  switched off in the app.** They only respond to `ATECH_PROMPT_OFF`.
  `firmware_on` depends on whether `import atech` works on that computer.
  → An "Agent features" section in Settings.
- **N26. Agent settings are split** between the sidebar switch and the
  Settings dialog, which treat environment overrides differently. → One
  summary line ("Quality · CAD + electronics · levels on · ~$25/reply").

**Accessibility**

- **N11. The pill switches are custom-drawn.** VoiceOver doesn't announce
  their choices, and they only take Tab focus.
- **N12. The board map shows no focus ring.** Port numbers are only in the
  picture; ring colours are hard-coded white.
- **N13. Sidebar controls have no focus rings.** Two controls named
  "Parts" and "Parts panel" do the same thing.
- **N14. The macOS bundle, Dock and ⌘Tab say "Atech Atelier"** while the
  UI says "Atech AI CAD".
- **N27. The module slide ignores reduce-motion settings**, and blocks the
  panel for 450 ms on every add, move and remove.

**Speed (board look)**

- **N16. 157 MB of Python lists held forever** (`board_look.py:266`).
  → Cache numpy arrays.
- **N17. Every object gets its own full-resolution scene with no
  normals.** For example the knob is about 150k triangles per copy.
  → Share nodes within a document, precompute normals, use a lower-detail
  mesh.
- **N18. The look builds on the GUI thread**, including a cold
  `measure_board()` (about 0.75 s). It also polls every 250 ms while a
  dialog is open.
- **N19. A failed load is cached until restart.** The `StudioLook` setting
  has no switch in the app.
- **N20. The picker redraws its icon every 3 s while idle.**
  `style.icon` has no cache. → Cache icons; drop the picker from the tick.

**Builds: modules and wires**

- **N29. Ports 8 and 12 are reserved but used** ("Do these first" #4).
- The round-1 module plan is in main and works. With FreeCAD 1.1.4,
  `./check` warns "MODULES: the board carries only the usbc" on a board
  with only USB-C. It stays quiet on a model whose eyes (distance sensor)
  and motor are cabled to their places, and then asks for holders for the
  cabled modules, as it should.
