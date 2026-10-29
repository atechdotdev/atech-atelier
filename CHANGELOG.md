# Changelog

All notable changes to Atech Atelier are listed here. Versions follow
[Semantic Versioning](https://semver.org). Before 1.0.0, any release may
change behaviour.

## [Unreleased]

### Parts you can buy, ready to use

- New on the Modules page: "Add off-the-shelf part…". Pick from about 75
  common parts as real 3D models: Arduino Nano, Uno and Mega, ESP32,
  Raspberry Pi 4 and Pico, servos, TT and metal gear motors, steppers,
  fans, AA/AAA cells and holders, a LiPo cell, a buck converter, motor
  drivers, panel buttons, switches, knobs, LEDs, displays, distance
  sensors, a Pi camera and USB, HDMI, Ethernet and audio sockets.
- Search them or pick a kind; see a picture, the measured size and the
  wiring. Install one and it joins your parts: the agent designs around
  it, with notes on what each needs (an opening for a sensor, air for a
  fan, a door for batteries).
- The models come from the FreeCAD Parts Library (CC BY 3.0). Each part
  keeps its authors' names, and every download is checked before it is
  used.

### Five more Atech modules

- New on the Modules page: Camera, Big Screen, Soil Sensor, Load Cell
  Amplifier and Power Jack, from Atech's own simulation models
  (atech-module-simready). They seat on the board, show in the 3D view
  with their real colours and the agent designs around them like any
  module: the soil probe sticks out through a wall, the camera gets a lens
  opening, the power jack's socket faces out of the case.
- The camera and big screen are Atech's CAD. The soil sensor, load cell and
  power jack are drawn from Atech's renders on a real Atech case and pin
  header: the parts on top are placeholders, and the app says so.
- The power jack plugs into one port but covers the next one along; the
  check stops another module going there.
- Atech's software has no drivers for these five yet, so the agent writes
  no firmware for them.
- Not yet: the Micro-SD module. Its model's pins sit 0.13 mm off the
  board's socket, so it would not fit. It comes once the model is fixed.

### Open source, with credit to Atech and FreeCAD

- Atech's code is now licensed under the GNU LGPL v3 or later, with one
  added term: anyone who shares, sells or builds a product on it must keep
  "Based on Atech Atelier by Atech, built on FreeCAD" in their app's credits
  and documentation (`LICENSE-ATTRIBUTION.md`). It was LGPL v2.1 or later;
  releases up to 0.1.2 keep that licence. The module models stay
  CC BY-NC 4.0.
- The FreeCAD logo now sits under the Atech Atelier name, on Home and in the
  sidebar, as "Based on FreeCAD". Click it to open freecad.org.
- The app is called Atech Atelier everywhere again, as its window, its icon
  and its folders always were (0.1.2 showed "Atech AI CAD" inside the app).
  Pictures and videos now go to the "Atech Atelier" folders.

### Real parts from NVIDIA SimReady

- **Install from NVIDIA SimReady…** on the Modules page searches NVIDIA's
  free library of real-object models (2,600 of them: batteries, fuses,
  bulbs, sensors, cameras, bolts and nuts, and much more), with a picture,
  size and weight for each. Electrical only and Fits on a desk are on by
  default.
- Install one and it joins your parts, ready to place beside the board or
  to have the agent build around. Each file is checked against the
  dataset's own record before it is used, and each part keeps NVIDIA's
  credit (CC BY 4.0).
- The first install also fetches the USD reader (about 40 MB, once).
- These are simulation models, not datasheets: a size can be a few
  millimetres off the real part (NVIDIA's 9 V battery is 53 mm tall; a
  real one is 48.5 mm). Atelier uses the size it measures and tells the
  agent to use the real datasheet where a fit matters.

### Your own parts, not only Atech modules

- **Import part…** on the Modules page brings in a part from another
  maker: an Arduino, a Raspberry Pi, a battery holder, a servo. Read from
  STEP, IGES, STL, OBJ, PLY or 3MF, in millimetres, inches, centimetres
  or metres. Its size is measured from the file. Say how it connects
  (I2C, UART, power...), its voltage, where its connectors are and
  anything the design must respect; the design agent gets all of it.
- Imported parts are kept in your own parts library, next to Atech's and
  never inside it, so an update leaves them alone. Right-click one to
  remove it.
- A part made with a real Atech 6-pin header (a board of your own built
  for the Atech connector) seats on the board like any Atech module.
  Every other part is placed by hand, and the agent builds the product
  around it: a cradle or standoffs, openings for its connectors, a route
  for its wires.
- A file that measures metres across (the wrong units) is refused with
  the fix, instead of being imported a thousand times too big.

### A clear way back to all your projects

- The sidebar has an **All projects** button at the top. On Home, while a
  project is open, it reads **Back to project**. The logo, Ctrl+0 and the
  project menu's "All projects" still work too.

### Exploded view and hand edits: nothing gets lost

- The exploded view only changes the picture, whatever else you do. A
  part you move while the parts are apart keeps that move when they go
  back together; Undo while apart puts the part back where it was, not
  somewhere in between; and a file can no longer be saved with its parts
  still pulled apart (using the menu's Exploded view and E together could
  do that).
- **Exploded view (E)** in the right-click and Atech menus now does the
  same as E and the view-bar button: one click apart, one click back.
  How far apart is the slider in **Show and hide**.
- Edit shapes puts an exploded view back together when it opens and
  before each change, so its numbers and its Undo are where the parts
  really are. Export for print and the review sheet always show the
  product assembled.
- Pressing Enter in an Edit shapes box no longer also adds a box shape.
- **Show and hide** opens above its button when there is no room below
  (it opened partly off the bottom of the screen).
- Deleting a part the design agent built now says that the next build
  brings it back, and offers to hide it instead (a hidden part stays
  hidden after every build).

## [0.1.2] - 2026-10-27 (preview)

### Five new Atech hardware examples

- Five more detailed examples on Home's **Start from an example** row,
  built to show off the Atech modules, the newer ones too: a **4WD
  explorer rover** (four DC motors, each on its N20 wheel hub, a distance
  sensor in the nose, an orientation sensor and lights), a **room air
  monitor** (the SCD40 CO2 sensor and the temperature / humidity sensor
  in a vented chamber, a screen and a status light), a **motion night
  light** (the PIR motion sensor behind an open window, lights behind a
  frosted moon diffuser and a mode key), a **robot arm dock** (the
  SO-101 robot arm integrator on a UART port, a screen and controls, and a
  marked mounting plate for the arm's base) and a **self-balancing
  robot** (two DC motors on N20 wheel hubs, a level orientation sensor at
  its centre, a tall narrow body with a screen face).
- As with the other examples: only ports the firmware can drive (never 8
  or 12; the robot arm on port 3 or 4, its UART ports), each passes
  `./check`, and so does every RESTYLE knob at its minimum and maximum.
- Asking for one of these ("a rover", "a CO2 monitor", "a motion sensor
  light", "a robot arm base", "a balancing robot") starts from the
  matching example. Their words go first, so "a robot arm" no longer starts
  from the desk robot, and "a motion sensor night light" no longer from the
  bedside lamp ("a night light" still does).

### The toy car has four motors

- The **toy car** example now has an Atech DC motor in every wheel: the
  rear pair seated on ports 1 and 9 as before, the front pair cabled from
  ports 5 and 13 and held in saddles in the chassis, each driving its
  wheel directly. The headlight and distance-sensor ribbons are re-routed
  round them, each in its own lane.

### Fixed

- A build started just before the Mac went to sleep (lid closed) could
  stop with "did not finish in 180 s" even though it needed under a
  minute. The build time limit now counts only time the computer is
  awake.

### Ten new starter examples

- New detailed examples on Home's **Start from an example** row:
  **smart planter, pet feeder, video doorbell, mini arcade, music box,
  parking sensor, desk organizer, photo frame, metronome and macro pad.**
  Each is a complete product around real Atech modules on ports the
  firmware can drive (never 8 or 12): screw bosses, an opening for every
  working face, lenses, grilles and key caps. Each passes the agent's own
  `./check`, and so does every style variation of it (each RESTYLE knob at
  its minimum and maximum).
- Asking the agent for one of these products ("a doorbell", "an arcade
  game", "a pencil holder", "a garage parking sensor") now starts from the
  matching example. The new product words go first, so "a pet feeder" no
  longer starts from the desk robot, and "an arcade game" no longer from
  the handheld console.

### Fixed

- The desk robot and smart speaker examples failed `./check` again
  ("microphone_p5_4: interference FAIL"). The imported SimReady microphone
  mesh sits 0.05 mm off the board's 4+5 socket pitch, so a microphone on
  ports 4+5 grazed the socket. The library microphone mesh is used for fit
  checks again, and its 3D look is unchanged (models/SIMREADY.json says
  why).

### Edit shapes by hand, TinkerCAD style

- A new **Edit shapes** window: view bar button, or press **R**. It follows
  what you select.
- **Add a shape:** box, cylinder, sphere, cone, torus or roof, 20 mm, set
  down beside the model.
- **Size:** type the exact width, depth and height in mm, with **Keep
  proportions**. A part keeps its footprint centre and its bottom when it
  grows. This works for imported **STEP**, IGES and BREP parts (the solid
  is scaled) and STL/3MF meshes, as well as for the shapes above (their
  own numbers change). A cylinder made oval becomes a plain solid of
  exactly that size, and the window says so.
- **Position:** X and Y (the footprint centre) and the elevation (the
  bottom). The arrow keys nudge by the chosen step; Shift moves up and down.
- **Turn:** 90° about Z, and tilts about X and Y. A tilted part stays on
  the floor.
- **Solid / Hole:** a hole is cut out of the solids it is combined with.
  **Combine** uses FreeCAD's own fuse and cut, so the parts stay editable
  under it; **Ungroup** takes it apart. **Duplicate** and **Delete** too.
- Every change is one undo step.
- Parts the agent built keep their sizes in **Dimensions** (D) or in the
  chat, so its next build can't silently undo a typed size; the window
  says so and opens Dimensions. Atech hardware keeps its real size.

### Home from anywhere

- **Home** (all your projects and the examples) now opens over the 3D view
  while projects are open. Click the Atech logo at the top of the sidebar,
  press **Ctrl+0** (⌘0), or choose **All projects (Home)** at the top of
  the project menu. Opening a project from Home, or **Esc**, goes back.

### Agent: products that work (Atech SDK)

- An Atech product now gets its **firmware** as well as its CAD: beside
  model.py the agent writes a `project.yaml` for the
  [Atech SDK](https://github.com/atechdotdev/python-sdk) (`atech build`,
  `atech upload`). It lists every module on the ports the build used, and
  its `code:` block makes the product do its job.
- Every workspace gets `reference/ATECH_FIRMWARE.md`, which is generated from
  the SDK's own catalog: each module's SDK id, methods, events, actions and
  cautions, plus the ports and port pairs the firmware accepts. The installed
  `atech` package is used when Studio's Python has it. Otherwise the
  snapshot shipped with the kit is used (SDK 1.0.0a11).
- The design levels' MODULE PLAN names what the firmware does with each
  module.
- `./check` prints the build's project.yaml modules block and FIRMWARE
  warnings: a port the SDK refuses, a project.yaml that does not match the
  build, and code that reads Serial, blocks in `delay()`, uses GPIO numbers
  or calls a method the SDK does not have. These are warnings only, never a
  failure. Switch the whole feature off with `ATECH_PROMPT_OFF=firmware`.

### Modules: the SimReady models

- The module library now comes from Atech's
  [atech-module-simready](https://huggingface.co/datasets/atechdev/atech-module-simready)
  dataset (the module-renders v1.7 CAD). Every module but USB-C is updated.
- The **knob** has pins now, so it plugs into the board like any module
  instead of being placed by hand.
- Four new modules: **PIR motion sensor**, **CO2 sensor (SCD40)**, **robot
  arm integrator** and **stepper motor driver**. Atech has no CAD of these
  yet: their case, board and pins are real, but the parts on top are
  placeholders. The Modules page marks them "derived".
- **Connect by cable**: the Modules page can add a module off the board,
  beyond the picked port, wired to that port by a ribbon cable. Move it
  where the design needs it, then press Remake cable. Every module can be
  connected this way.

### Agent: design levels

- A new product is designed in **nine levels, one agent turn each**, the
  way a product design studio works: brief and rough volume, packaging the
  Atech board, surfaces and edges, the shell, modules with their openings
  and cable routes, 3D details, colour and material, refinement, and
  product ready. Each level has a checklist and a gate, and ends on a
  passing build before Atelier sends the next one, so the product improves
  step by step and a failure costs one level, not the whole design. The
  turn card shows the level ("Level 3/9: Shape the surfaces and smooth the
  edges"). Stop, a failed level, or a message of your own ends the run.
- A new product starts from the closest product example (toy car, desk
  robot, smart speaker, bedside lamp, handheld console), which already
  builds, so the 3D view shows a whole product at once instead of after
  10-20 minutes.
- The agent's instructions now set a real-world quality standard: the result
  must stand next to a real product of its kind.
- **Module plan.** Level 1's brief now plans the Atech modules a real
  product of its kind has, even ones the user didn't name, such as eyes
  (a distance sensor, or lights or the screen as a face), motors at the
  wheel, arm or fan they drive, lights, buttons and a speaker. Each one has
  a place on the product. A module whose job is at a place is cabled there
  with `ap.cable`, routed inside the body, instead of sitting wherever its
  port is. Level 2 places every module in the plan, and its gate checks
  them. `./check` warns when the board carries no module or only the USB-C
  (`ATECH_PROMPT_OFF=module_plan` turns the plan off).
- `cad.detail("name")`: a detail that fails with a geometry error is skipped
  and listed by `./check` instead of failing the whole build.
- Each change can be switched off on its own for comparison
  (`ATECH_PROMPT_OFF=levels,seed_fork,real_world`). The eval harness drives
  the same levels, saves a render per level, and reports the level reached.

### macOS

- A macOS app for Apple silicon and Intel, built by
  `branding/build_macos.sh` from FreeCAD 1.1.3's official macOS disk images
  (pinned by sha256; refused unless the FreeCAD Project Association's
  signature on FreeCAD.app verifies). It carries the same Atech workbench,
  theme, module library and notices as the AppImage, passes the same build
  gate (`verify_tree.py`, now platform-aware), and lists every change in
  `ATECH_CHANGES.txt`. FreeCAD's program files and libraries keep their own
  signatures; only the bundle is re-signed (ad-hoc, or a Developer ID with
  notarization when configured).
- Design scripts run in the macOS sandbox (`sandbox-exec`): no network, no
  view of the home folders, `/Volumes` or the temp folders, writes only to
  the chat's folder, and `./check` read-only. Measured with a hostile
  model.py through both the app's build and `./check`. On Linux, bubblewrap
  as before.
- Claude Code runs started by the app are stopped when the app quits or
  crashes (macOS has no `PR_SET_PDEATHSIG`; a small watcher does it).
- Signing in opens Terminal.app; the bundle's own `bin/` and `Mod/` folders
  no longer leak into the `PATH` of Claude Code and the in-app terminal.
- The app never writes Python bytecode into its own bundle, which would
  break its code signature.

### Motors

- The **DC motor** module is offered on the Atech modules page and to the
  agent. It always seated (one connector), but the library filed it under
  `motor` and both only listed `module`. Its description now says what the
  hardware is: the N20 gearmotor sits inside the housing and its shaft
  comes out of the end face.
- A **NEMA 17 stepper motor** (`nema17_stepper`), the motor Atech's stepper
  driver drives, as an off-board part: placed with
  `atech_modules.load_module`, never seated. Its flange, M3 hole square,
  pilot and shaft are the NEMA standard; the body length and shaft length
  are stated as choices. The mesh is generated by `projects/gen_nema17.py`.
- The agent's API card lists off-board parts (the wheel, the NEMA 17) with
  their measured sizes and the call that places them, instead of as
  modules that "cannot be seated".

### Sidebar, as on studio.atech.dev

- A project picker at the top of the sidebar. Its menu lists the open
  projects, recent files, a new project, the Atech starter projects and
  Open file. Each project is a document with its own chat, so switching
  projects switches the chat.
- Two views instead of three tabs: **3D CAD** (the chat with the agent; the
  **Parts** button beside it shows the part tree) and **Atech modules**. The
  switch is Studio's two-tab pill with the sliding black thumb.
- The Atech modules page draws the board the way Studio does: the board's
  own plan-view picture with its port numbers, and each placed module's
  picture seated in its port and facing outward (Studio's sprites, rendered
  from the module models). A port you pick or point at gets a ring.
- The 3D view draws the board and modules as Studio does: the real models
  (atech-module-renders v1.5) with their own materials, meaning black
  shells, navy PCBs, gold pins, clear lids, lit LEDs, the board's printed
  port numbers and the "Atech" screen. It's display only: the STL meshes
  every fit check measures are unchanged, a click still selects the
  module, and nothing is written into your document. Each model is placed
  on its STL by a measured offset (tests/test_board_look.py). The knob's
  model is taller than the knob the checks measure (38.1 vs 29.9 mm).
  Turn the look off with the StudioLook preference.

### Install

- `install.sh`: one command for macOS and Linux
  (`curl -fsSL .../install.sh | bash`). It downloads the newest release for
  this computer, installs nothing unless the file matches the release's
  `SHA256SUMS` (and, on macOS, the app's signature verifies), needs no sudo,
  and checks for Claude Code. `--uninstall` removes the app and keeps your
  data.
- The release workflow builds the macOS disk images next to the AppImage
  and publishes one `SHA256SUMS` for all of them.

## [0.1.1] - 2026-10-04 (preview)

Credits and licence notices corrected. No change to the bundled components:
the same pinned FreeCAD 1.1.3 image.

### Credits corrected

- Licence texts now shipped that 0.1.0 lacked, each taken from the
  component's official repository at the version in the image: the AppImage
  type-2 runtime (MIT), libfuse (LGPL-2.1), squashfuse (BSD-2-Clause), musl
  (MIT) and the FreeType License, alongside the Coin3D, SoQt, PCL,
  Xerces-C, zstd, LGPL-3.0 and GPL-3.0 texts.
- The AppImage runtime is now pinned to the exact file 0.1.0 carried
  (type2-runtime commit 8f39b89) instead of being fetched at pack time.
- Source code is attached to every release from 0.1.1 on: the FreeCAD 1.1.3
  source archive and this repository's source at the release tag.

- FreeCAD's licence is now stated as FreeCAD states it: "LGPL2+" (the GNU
  LGPL version 2 or any later version), from its `LICENSE.html` and About
  banner, noting that its repository `LICENSE` file is the LGPL 2.1 text
  and many source files carry SPDX LGPL-2.1-or-later. The 0.1.0 binary's
  notices said "LGPL-2.1-or-later" without this context (About box, NOTICE,
  CREDITS.md, README, `ATECH_CHANGES.txt`, AppStream metainfo).
- FreeCAD's copyright line is now upstream's own banner, verbatim:
  "(C) 2001-2026 FreeCAD contributors" (Jürgen Riegel credited as the
  person who started FreeCAD in 2001).
- "Atech Atelier is FreeCAD" is now "Atech Atelier is built on FreeCAD".
- "Unmodified" now says what is unmodified: FreeCAD's program files.
  Atech changes AppRun, the icon and the desktop/AppStream entries, and
  adds a branding file (CREDITS, NOTICE, README, metainfo, CHANGELOG).
- Added the FreeCAD Project Association: the FreeCAD logo is its registered
  trademark (Benelux); not endorsed by or affiliated with the FreeCAD
  project or the FPA. Also not endorsed by or affiliated with Anthropic.
- The About box comment no longer claims the LGPL forbids implying
  endorsement; that comes from the FPA's trademark and brand guidelines.
- AppStream: `project_license` is documented as covering Atech's own files
  only.
- Newly credited bundled components: CalculiX, FFmpeg, x264, x265 (all
  GPL-2.0-or-later), GNU Readline (GPL-3.0), IfcOpenShell
  (LGPL-3.0-or-later), Netgen inside SMESH, the components FreeCAD compiles
  in (KDL, libarea, Ondsel Solver, PyCXX, Zipios++), and the other copyleft
  packages (pythonocc-core, CGAL, MPFR/GMP/MPC, MySQL client, libgfortran).
- Newly credited Atech additions: the AppImage type-2 runtime (MIT) and the
  libraries it statically links (libfuse 3.15.0, squashfuse 0.5.2, musl,
  libzstd, zlib); the theme files derived from FreeCAD's (LGPL2+, modified
  by Atech); opencode (MIT, not bundled, optional engine).
- Corrected licence entries: Qt (LGPL-3.0 for the modules FreeCAD uses;
  some shipped modules are GPL-3.0 only), PySide6 (LGPL-3.0 OR GPL-2.0 OR
  GPL-3.0), SMESH (LGPL-2.1-or-later, linked 9.9.0.0), Gmsh (copyright and
  how FreeCAD runs it), Pivy (notice in its `__init__.py`), FreeType (FTL,
  dual-licensed with GPL-2.0-or-later) with the FTL credit sentence.
- Licence texts now shipped in `usr/share/doc/atech-atelier/third_party/`:
  Coin3D, SoQt, Point Cloud Library, Xerces-C (Apache-2.0), libzstd, and
  the GNU LGPL v3 and GPL v3.
- FreeCADMCP is described as what it is: an optional XML-RPC server, off by
  default, that Atech Atelier's own agent does not use.
- Lucide: copyright year added (2026); the icon path data is from older
  Lucide releases (e.g. tag 0.400.0), not from the commit the licence was
  fetched at; "chat" is Feather's. Feather: both copyright notices given
  (2013-present per Lucide's licence, 2013-2023 in Feather's own).
- The UI font fallback order is stated exactly.
- appimagetool: version 1.9.1 (git 8c8c91f) recorded; it was listed as
  "not determined".
- `SOURCE_OFFER.txt`: the package count (326, not "roughly 300"), the
  feedstock names (often not `<package>-feedstock`), no claim that
  anaconda.org links each build's source archive, an "AppImage runtime"
  section, and a full written-offer text used once a contact is set. Until
  then the file says plainly that it carries no written offer. When a
  contact was set, the old text also appended the contact address after
  the offer; fixed.
- `ATECH_CHANGES.txt` records the change date.
- `LICENSE-models.md`: copyright year (2026), the CC BY-NC 4.0 conditions
  (keep notices, link the licence, indicate changes) and a modification
  mark in the suggested attribution.
- The licences grant no right to use the Atech names or logos except to say
  where the software comes from.

## [0.1.0] - 2026-10-03 (preview; published 23:31 UTC)

The first public preview.

### What it is

- Atech Atelier is the official FreeCAD 1.1.3 Linux AppImage with FreeCAD's
  program files unmodified. Atech changes only AppRun, the icon and the
  desktop/AppStream entries, and adds the Atech workbench, branding and
  module library (every change is listed in `ATECH_CHANGES.txt` under
  `usr/share/doc/`).
- Linux x86_64 only, as a single AppImage.

### Added

- A chat panel: describe a part in plain language. The agent writes a
  FreeCAD script, runs it, measures the result and shows it in the 3D view.
  The model stays an ordinary FreeCAD model you can edit.
- Three agent engines, chosen in Agent Settings: Claude Code (the default,
  and the one this release is tested with), a local OpenCode server, or a
  provider API token.
- The Atech module library: the 14-port board and its plug-in modules, with
  their meshes bundled in the image. The Modules page and the
  Atech > New Project menu place them.
- A light and a dark theme, generated from one set of brand colour tokens.
- Credits for FreeCAD and every bundled open-source component, with the
  location of each licence text inside the image.

### Licences

- Atech's code: GNU LGPL v2.1 or later (`LICENSE`).
- Atech board and module models and `presets.yaml`: CC BY-NC 4.0
  (`LICENSE-models.md`).
- FreeCAD and its bundled libraries keep their own licences (`CREDITS.md`).

### Known limits

- Preview quality. Settings and file locations may change before 1.0.0.
- No automatic updates.
