# Atech Atelier

*Atech Atelier, powered by FreeCAD.*

Atech Atelier is a CAD app you talk to. Describe a part in plain language,
such as *"a 40 mm cube with a 10 mm hole through the middle"*, and the agent
writes a FreeCAD script, runs it, **measures** the result and shows it in the
3D view. The volumes and sizes it reports are measured off the solid. The
result is an ordinary FreeCAD model, so you can keep editing it by hand,
save it as `.FCStd` or export it as STEP or STL for printing.

It also knows the Atech hardware: the 14-port board and its plug-in modules
ship inside the app, so you can design enclosures and parts around real
modules that sit where they really go.

Atech Atelier is the official, **unmodified** FreeCAD 1.1.3 release with the
Atech workbench, theme and module library added. It comes as one Linux
AppImage (x86_64), and nothing is installed system-wide.

> Atech Atelier is built on FreeCAD (LGPL-2.1-or-later). It is not endorsed
> by, affiliated with, or a product of the FreeCAD project.

**Status: 0.1.0, a preview.** Expect rough edges, and please report them.

---

## Screenshots

<!-- RELEASE: add screenshots before publishing. Planned list: -->

1. The chat beside the 3D view, building a part from one sentence.
2. A finished part with its measured volume and size in the reply.
3. The Modules page: placing a module on the Atech board.
4. An enclosure designed around seated Atech modules.
5. Light and dark themes.

---

## Requirements

- **Linux, x86_64**, with a desktop session.
- **FUSE 2** to run AppImages directly (most desktops have it). Without it,
  see [Troubleshooting](#troubleshooting).
- **Claude Code**, Anthropic's command-line agent, installed and signed in.
  The chat runs on it, and Atech Atelier does not include it. Claude Code
  needs a Claude account that includes it; see Anthropic's setup page
  (<https://code.claude.com/docs/en/setup>) for which plans do.
- **Optional: bubblewrap** (`bwrap`). When it is installed, every design
  script runs in an isolated sandbox: read-only system, no network, no view
  of your home folder. Without it the app still works, and tells you once
  what a design script can still reach. On Debian/Ubuntu: `sudo apt install bubblewrap`.

## Download and run

<!-- RELEASE: the public repo atechdotdev/atech-atelier is PROPOSED (ADR-006)
     and does not exist yet. Check this link once it is created. -->
Download `AtechAtelier-<version>-x86_64.AppImage` and `SHA256SUMS` from
the [Releases page](https://github.com/atechdotdev/atech-atelier/releases),
then, in the folder you downloaded them to:

```bash
sha256sum -c --ignore-missing SHA256SUMS
chmod +x AtechAtelier-*-x86_64.AppImage
./AtechAtelier-*-x86_64.AppImage
```

Atech Atelier opens on its own workbench with the chat on the right.

## Set up Claude Code (once)

### 1. Install it

The installer recommended on Anthropic's setup page
(<https://code.claude.com/docs/en/setup>):

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

It puts the `claude` command in `~/.local/bin/claude`, the first place Atech
Atelier looks. Check that it works:

```bash
claude --version
```

### 2. Sign in

```bash
claude auth login
```

Follow the steps it shows (it opens your browser). On an older Claude Code
without `claude auth`, run `claude`, type `/login`, and `/exit` when done.
Check it with:

```bash
claude auth status
```

Atech Atelier uses this same sign-in. It never asks for your password or an
API key.

If you skip either step, the chat tells you what is missing and shows the
same commands, as text you can copy, with a **Retry** button.

### 3. Build something

Type a request in the chat and press Enter. Before your first message is
sent, the app shows what leaves your computer (below) and asks you to
continue.

## Atech modules

The **Modules** page and the **Atech → New Project** menu place real Atech
hardware modules (the 14-port board and its plug-in modules) from the library
inside the app. Nothing extra is downloaded. If the page says *"Atech modules
are missing from this installation"*, the download is incomplete: download it
again.

## Privacy: what is sent, and what is stored

The chat runs Claude Code **on your computer**, signed in to **your own**
Claude account. Atech does not run a server, and nothing goes to Atech.

**Sent to Anthropic**, through your Claude Code account, each time you send a
chat message:

- what you type;
- a summary of the open document: its name, each solid's name, volume and
  size, the Atech board and modules on it, and what you have selected in the
  3D view;
- any picture of the 3D view you attach with **Add view** or **Ask about this
  view**;
- the files the agent reads in that chat's own folder while it works: its
  design script, the pictures it renders of its own build to check it,
  the Atech reference files copied there, and what its build check
  (`./check`) prints, measurements included. The agent is started with that
  folder as its only working folder.

Claude Code also includes what it adds to any session, such as the chat
folder's path and the name of your operating system. What Anthropic does with
all of this is set by the terms of your Claude account.

**Stored on your computer:**

| what | where |
|---|---|
| one folder per chat (design script, pictures) | `~/.local/share/Atech Atelier/v1-1/agent/` |
| the list of agent builds you accepted, and which chat belongs to which document | `~/.local/share/Atech Atelier/v1-1/AcadAgent/`, `.../agent/sessions.json` |
| the design script of every document the agent built into | inside that `.FCStd` file, wherever you save it |
| Agent Settings (engine, model, budget, `claude` path) | `~/.config/acadagent/settings.json` |
| app preferences (theme, layout) | `~/.config/Atech Atelier/` and `~/.config/Atech/` |
| cache | `~/.cache/Atech Atelier/` |
| Claude Code's own conversation history | `~/.claude/` (managed by Claude Code) |

Chat folders are kept until you delete them: **Agent Settings → Clear old chat
workspaces**. To reset Atech Atelier completely, close it and delete the
folders above.

Your normal FreeCAD installation, its settings and its addons are not
touched: Atech Atelier keeps its own profile.

## Troubleshooting

**"Permission denied" when starting.** Run `chmod +x` on the file (see
above).

**"AppImages require FUSE to run" / `libfuse.so.2` not found.** Install FUSE 2
from your distribution (Ubuntu 24.04: `sudo apt install libfuse2t64`; Ubuntu
22.04: `sudo apt install libfuse2`), or run without FUSE:

```bash
./AtechAtelier-*-x86_64.AppImage --appimage-extract-and-run
```

**The chat says Claude Code is not found.** Check `claude --version` in a
terminal. If it works there but not in the app, the app does not see the same
`PATH` (a shell function or alias does not count). Set the full path to the
program in **Agent Settings** (for the official installer:
`~/.local/bin/claude`).

**The chat says you are not signed in.** Run `claude auth login` in a terminal,
then press **Retry** in the chat.

**The 3D view is empty on first start.** Use **Atech → Open Sample Crane** to
load the bundled example.

**Anything else.** Start the app from a terminal and keep what it prints. The
Report view (*View → Panels → Report view*) also shows errors from inside the
app.

## Licences

Atech Atelier contains parts under different licences. Each applies only to
its own files.

| what | licence | text |
|---|---|---|
| Atech's code: the Atech workbench (`addon/AcadAgent`), the branding and build scripts | **LGPL-2.1-or-later** | [`LICENSE`](LICENSE) |
| Atech board and module 3D models, and `presets.yaml` | **CC BY-NC 4.0**: free for any non-commercial use, with credit to Atech | [`LICENSE-models.md`](LICENSE-models.md) |
| FreeCAD and the libraries it bundles | their own licences (FreeCAD: LGPL-2.1-or-later) | `usr/share/doc/FreeCAD/` in the app |
| third-party components Atech added (FreeCADMCP, Lucide, Feather) | their own licences | `usr/share/doc/atech-atelier/third_party/` in the app |

Inside the app, `usr/share/doc/atech-atelier/` also holds `SOURCE_OFFER.txt`
(where to get the source) and `ATECH_CHANGES.txt` (every file Atech added or
changed compared with the upstream FreeCAD image, measured file by file). To
browse them without running the app:
`./AtechAtelier-*-x86_64.AppImage --appimage-extract`, then look under
`squashfs-root/usr/share/doc/`.

Claude Code is a proprietary Anthropic product. It is **not** part of Atech
Atelier: the app runs the copy you installed, under Anthropic's terms.

## Credits

Atech Atelier stands on FreeCAD. Thank you to the FreeCAD project and its
community for the modeller, the geometry kernel integration and the whole
application this is built on, and to the people behind Open CASCADE, Qt,
Coin3D, Python and the many other open-source projects FreeCAD brings with it.

[`CREDITS.md`](CREDITS.md) lists every project we build on or ship, with the
version we ship, its licence and where its licence text is in the app. In the
app: *Help → Credits & Open-Source Licences* (also in the *Atech* menu).

## Building from source

The AppImage is assembled from the official FreeCAD 1.1.3 AppImage (fetched
from FreeCAD's GitHub release and checked against a pinned sha256), the Atech
workbench and branding in this repository, and the Atech module library.
FreeCAD itself is not recompiled.

```bash
./branding/build_appimage.sh --tree-only   # build and verify the app folder
./branding/build_appimage.sh               # ...and pack it into dist/AtechAtelier-<version>-x86_64.AppImage
dist/build/squashfs-root/AppRun            # run the built folder directly
```

Packing needs `appimagetool`. The build also needs python3 with numpy, Pillow
and scipy, inkscape, curl, and the Atech module library (`--artifacts DIR`).
The build checks itself and fails loudly when anything is missing. See
[`branding/README.md`](branding/README.md) for every option and dependency.
