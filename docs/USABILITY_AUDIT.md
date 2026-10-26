# Usability audit: 100 standard desktop-app issues

Atech AI CAD (formerly Atech Atelier) was checked against 100 common
desktop-app usability problems, on 2026-10-26 on the `macos-support` branch.
Each line gives a status, where the code stands and the fix. Paths are under
`addon/AcadAgent/acadagent/` unless they say otherwise.

**OK** = done · **PARTIAL** = some of it is done · **MISSING** = not done

Totals: 25 OK · 60 PARTIAL · 15 MISSING

## Do these first

These have the most effect for the least work, roughly in order.

1. **Finish the rename to AI CAD (#19, #15, #58).** Only the in-app labels say
   "AI CAD". The window title, About box, bundle name, DMG name, `.desktop`
   file, data folder and about 20 messages still say "Atech Atelier", and
   the README describes data paths that don't exist yet. Switch the branding
   constants, the migration and the README together, then add a CI grep that
   fails on "Atelier" in text users see.
2. **Help, About and Report a problem (#13, #16, #17, #20).** The Help menu
   has only Credits. Add Help, Discord, What's new, About (with the Atech,
   FreeCAD and Claude Code versions and a Copy button) and "Report a problem"
   (versions plus redacted logs, opening a pre-filled GitHub issue).
3. **Usage-limit, rate-limit and overload errors (#23, #99).**
   `classify_failure` doesn't recognise them, so they show a generic "The
   agent stopped" message. Add a LIMIT class that shows the reset time and
   doesn't offer an immediate Retry.
4. **Offline shows "Agent ready" (#85).** `panel.py:6067` sets the state to
   idle before showing the offline notice. Set it to "No connection" instead,
   and say that CAD, measuring and export still work without a connection.
5. **Attach your own picture to a chat message (#38, #75, #76, #96).**
   Pasting, dropping or picking an image into the chat box should attach it
   with `add_shot`, the same way a 3D-view capture is attached today.
6. **Actions after "The build still fails" (#25).** Add Try again, Go back
   to the last good build, and Copy error.
7. **Export blocks the window (#41, #42, #43).** `export_for_print` meshes
   and writes on the GUI thread. Move it to a worker, with progress and
   Cancel, and remember the last export folder (#37).
8. **Queue a message while the agent is busy (#50, #92).** Today it's
   refused. Offer "Send after this reply" and "Stop and send".
9. **Text size and contrast (#61, #63, #67).** There are 137 hard-coded px
   font sizes, and the `dim` colour fails WCAG AA in both themes. Use size
   tokens based on the system font, darken or lighten `dim`, and add a chat
   text size setting with Ctrl+= / Ctrl+-.
10. **Check for updates and show what's new (#11, #12).** Check GitHub's
    latest release once a day off the GUI thread, and show the CHANGELOG
    section after an update.

## A. Install, first run, onboarding

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 1 | Needs the terminal to install | PARTIAL | A DMG exists (`branding/build_macos.sh:642`), but the README sends users to `install.sh --file` when a release isn't notarized. → Notarize every release in `release.yml`; make the DMG the main path. |
| 2 | Gatekeeper warnings | PARTIAL | Covered only in the README; the build prints "SKIPPED" when there's no notary profile. → `publish_release.sh` refuses macOS assets that aren't notarized; add "Open Anyway" steps to the release notes. |
| 3 | Claude Code missing | PARTIAL | Detected (`panel.py:2468`), with Retry and Settings only. → Add an "Install Claude Code" action that runs `INSTALL_COMMAND` in Terminal and checks again when it closes. |
| 4 | First-run tour | PARTIAL | A welcome card, sample prompts and an orbit hint exist; no tour. → A 3-step one-time coachmark (chat, project picker, view bar). |
| 5 | Empty states | OK | Chat, projects and the 3D view all say what to do. |
| 6 | Signed out of Claude | PARTIAL | Detected (`claude_cli.py:572`), but "Open terminal" starts bare `claude`. → Run `claude auth login`, and check `auth_status()` until it passes, then clear the notice. |
| 7 | Examples are easy to find | OK | Examples row on Home, prompt chips, sample crane. |
| 8 | Too much FreeCAD chrome | PARTIAL | Toolbars are hidden; the full FreeCAD menu bar is not. → Hide Macro/Tools/Windows while Atech is active, with a "Show full FreeCAD menus" option. |
| 9 | Opens on the right page | OK | `StartWorkbench` is set and the Start page is hidden. → Optionally switch to the Atech workbench at startup if the user last quit in another one. |
| 10 | Startup feedback | OK | Branded splash; slow work is deferred. → The dark splash is shipped but never used. |

## B. Updates, versions, uninstall, support

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 11 | No update check | MISSING | → Check the latest GitHub release daily; show a notice with Update. |
| 12 | No "What's new" | MISSING | → Ship CHANGELOG.md; remember `last_seen_version`; show that version's section. |
| 13 | Version not visible | MISSING | The About box shows FreeCAD only; `__init__.__version__` says 0.1.0 while VERSION says 0.1.1. → Set it from VERSION at build time; add an Atech About dialog. |
| 14 | Uninstall leaves data behind | PARTIAL | `install.sh --uninstall` lists only some of the data folders. → Add `--purge`, and list `~/.config/acadagent` and the projects folder. |
| 15 | Data migration between names | PARTIAL (risk) | `migrate.py` handles only "Atech Studio", on Linux only. → Accept a list of old names, add macOS paths, and do this before ExeName changes. |
| 16 | No bug report from the app | MISSING | → "Report a problem…" in the gear and Help menus. |
| 17 | Logs hard to find | PARTIAL | Logs go only to the FreeCAD Report view. → A rotating `atech.log` plus "Show logs". |
| 18 | No setup check | PARTIAL | The checks exist but are scattered. → A "Check setup" dialog: Claude installed, signed in, sandbox, freecadcmd, projects folder writable, FUSE/bwrap. |
| 19 | Mixed product name | PARTIAL | See "Do these first", item 1. |
| 20 | No help in the app | MISSING | The Help menu has only Credits. → Add Help, Discord, What's new, About. |

## C. Errors, messages, recovery

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 21 | Raw tracebacks | OK | `Notice` hides details behind a "Details" button. → Optionally add a plain first line to build errors. |
| 22 | Errors without a next step | PARTIAL | About 30 notices end with "The details are in the Report view." → Give a concrete next step and a Copy details button. |
| 23 | Network and API errors | PARTIAL | No handling for usage limits, 429, overloaded or 5xx. → New LIMIT and OVERLOADED classes. |
| 24 | Errors swallowed silently | PARTIAL | 109 `except Exception: pass` blocks. → Log them, starting with `export_tools.py` and `projects_store.py`. |
| 25 | Failed build gives no options | PARTIAL | After the automatic fixes run out, no buttons. → Try again / Last good build / Copy error. |
| 26 | Hung processes | OK | Sandbox kill, stall watchdog, exit watchdog. → Optionally a hard per-turn limit. |
| 27 | Error popups block the app | OK | In-chat notices. → Show `navbar._warn` as a notice too. |
| 28 | Errors can't be copied | PARTIAL | Mouse-selectable only. → Copy details button. |
| 29 | Jargon | PARTIAL | "bwrap", "sandbox-exec", "Report view" and ".FCStd" appear in messages. → Rewrite them in plain language. |
| 30 | Claude Code crash mid-turn | OK | The panel returns to its normal state. → Add a test that kills the process mid-turn. |

## D. Keeping your work safe

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 31 | Autosave | OK | Every 60 s, plus after each build. |
| 32 | Crash recovery | OK | FreeCAD's recovery is turned on. → Check the recovery dialog still appears under the Atech layout. |
| 33 | Undo agent changes | OK | Transactions plus "Go back to this build". |
| 34 | History of builds | OK | 60 builds kept per chat. → A per-chat History list. |
| 35 | Unsaved changes on quit | OK | |
| 36 | Deleting safely | PARTIAL | Projects go to the Trash; "Clear old chat workspaces" deletes for good, and old chats drop silently past 20. → Move to Trash, and warn before dropping. |
| 37 | Export defaults | PARTIAL | Always saves to Desktop by default. → Remember the last folder, falling back to the project's folder. |
| 38 | Opening files | PARTIAL (bug) | The panel's "Open file…" leaves out STL/3MF and opens STEP with the wrong API (`panel.py:2711`). → Use `shell.open_path`. |
| 39 | Where data lives | OK/PARTIAL | → Show in Finder next to the projects folder, plus the chat-data size. |
| 40 | Disk use grows | PARTIAL | Chat folders cut from the list aren't deleted. → Delete them in `_park_chat`; delete old ones at startup. |

## E. Speed and responsiveness

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 41 | Work on the GUI thread | PARTIAL | Export, share sheet, legacy `new_session`, autosave during a turn. → Move them to workers; skip autosave while busy. |
| 42 | Progress for long tasks | PARTIAL | Turns and builds show elapsed time; export and example builds show nothing. |
| 43 | Cancel | PARTIAL | No cancel for export, example builds or renders. |
| 44 | Streaming | OK | stream-json with partial messages. |
| 45 | Large models | OK | Coarse preview, then fine mesh at the end. |
| 46 | Memory over long sessions | PARTIAL | Chat widgets and per-document state are never pruned. → Prune when a document closes; collapse older messages. |
| 47 | Minimised or in the background | PARTIAL | Timers keep running. → Pause them while the app is inactive. |
| 48 | Addon startup cost | OK | → Time `shell.install()`; build the panel later if it's slow. |
| 49 | Timers while idle | PARTIAL | An 800 ms document poll and a 3 s tick run constantly. → Use observer signals. |
| 50 | Several requests at once | PARTIAL | A message sent while busy is refused. → Queue it. |

## F. Finding things, navigation, help

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 51 | Keyboard shortcuts | PARTIAL | No shortcut for new chat, Stop (Esc) or export. → Add to `SHORTCUTS` (`shell.py:2892`). |
| 52 | Command palette | MISSING | → Ctrl+K over the shortcuts, tools and export commands. |
| 53 | Tooltips | OK | → Add a test that every icon button has one. |
| 54 | Menu bar | PARTIAL | New chat, Stop, Past chats and export aren't in the Atech menu. |
| 55 | Right-click menus | PARTIAL | None on chat messages. → Copy, Retry from here, Edit and resend. |
| 56 | Where am I | OK | → Put the project name in the window title. |
| 57 | What can I ask | PARTIAL | No `/help` or slash commands. |
| 58 | Consistent wording | PARTIAL | Product name and menu capitalisation vary. |
| 59 | Back to Home | MISSING | Home shows only when no document is open. → A Home item with "← Back to <project>". |
| 60 | Search | PARTIAL | Projects can be searched; chats can't. → Ctrl+F in the chat; a filter on Past chats. |

## G. Accessibility and display

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 61 | Hard-coded pixel sizes | PARTIAL | 137 `font-size: NNpx`. → Size tokens based on the system font, in pt. |
| 62 | Follows light/dark | OK | → Fall back to `palette_is_dark()` when Linux reports Unknown. |
| 63 | Contrast | PARTIAL | `dim` is about 2.5:1 (light) and 3.2:1 (dark). → `#6b7280` / `#8a8a8a`. |
| 64 | Keyboard focus | PARTIAL | No tab order; some focus rings are missing. |
| 65 | Screen-reader names | PARTIAL | The Send/Stop button has none. |
| 66 | Small screens | PARTIAL | Dialogs aren't kept within the screen; fixed 220 px search box. |
| 67 | Text size | MISSING | → Chat text size setting. |
| 68 | Reduce motion | PARTIAL | The navbar slide ignores the system setting. |
| 69 | Translation and units | MISSING | No `translate()`; "mm" is hard-coded. |
| 70 | Icons in both themes | OK | → Delete `theme.py`, which nothing imports. |

## H. Fitting in with macOS and Linux

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 71 | Window layout remembered | PARTIAL | Sidebar width and the Parts split reset on every launch. |
| 72 | Several monitors | PARTIAL | No handling when the window moves to another screen. |
| 73 | macOS conventions | PARTIAL | ⌘, opens FreeCAD's preferences; ⌘P is taken by Parts; full screen is Ctrl+Shift+F. |
| 74 | File associations | OK | |
| 75 | Drag and drop | PARTIAL | Files can be dropped on the window, not into the chat box. |
| 76 | Clipboard | PARTIAL | Can't paste an image; no Copy on code blocks. |
| 77 | Notice when a turn ends | MISSING | → `QApplication.alert(mw)` when the window isn't in front. |
| 78 | Only one copy running | PARTIAL | → Set `SingleInstance` on macOS. |
| 79 | Sleep, wake, network changes | PARTIAL | → `QNetworkInformation` to pause the watchdog and show Offline. |
| 80 | Linux desktop | PARTIAL | Only an SVG icon; the app is forced to run under X11 (xcb). → PNG icon sizes; check WM_CLASS. |

## I. Settings, privacy, network

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 81 | Settings layout | PARTIAL | One flat form; no Restore defaults. → Sections plus Restore defaults. |
| 82 | When settings apply | PARTIAL | → "Applies from your next message." |
| 83 | Settings only reachable by env var | MISSING | 15 `ATECH_*` env vars can't be set in the app; `ATECH_PROMPT_MODE` overrides the Mode setting without telling the user. → Say when an env var is in effect; add a Safety section. |
| 84 | Privacy notice | PARTIAL | Shown only once. → "Data & privacy…" to show it again, plus "no telemetry". |
| 85 | Offline | PARTIAL (bug) | The pill says "Agent ready" while offline. |
| 86 | Proxy | MISSING | A Finder launch loses `HTTPS_PROXY`; `--setting-sources ""` also drops it. → Read the proxy variables from the login shell. |
| 87 | Units | MISSING | "Millimetres" and 0.2–0.3 mm clearances are hard-coded in the prompt. |
| 88 | Model and cost | OK | → Show token counts in a tooltip. |
| 89 | Secrets | OK | |
| 90 | What the agent can do | PARTIAL | Enforced, but not shown in the app. → A read-only "What the agent can do" row. |

## J. The chat and the agent

| # | Issue | Status | Where it stands → fix |
|---|---|---|---|
| 91 | How long a turn takes | OK | Elapsed time, "Level 3/9". → A typical-duration hint. |
| 92 | Changing course mid-turn | PARTIAL | A message is refused while busy. |
| 93 | Measured facts vs claims | PARTIAL | The empty state says "every size in a reply is measured", but sizes in the agent's text aren't. → A "Measured" badge on measured results; fix that wording. |
| 94 | Retry, edit and resend | PARTIAL | Only after a failure. |
| 95 | Managing chats | PARTIAL | Can't rename, delete one chat or export. |
| 96 | Attach a reference picture | PARTIAL | Only 3D-view captures. |
| 97 | Clarifying questions | MISSING (by design) | → Allow one question when a size only the user knows is missing; show the assumptions as chips the user can change. |
| 98 | Show the code | PARTIAL | → A "Show code" toggle with a diff between builds. |
| 99 | Usage limit | MISSING | See #23. |
| 100 | "This is wrong" feedback | PARTIAL | The 3D selection is sent with a message, but nothing shows that it will be. → A "Wrong" button and a "Selected: Body.Face6" chip. |
