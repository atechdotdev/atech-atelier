"""atech_levels - the DESIGN LEVELS: a new product is designed in gated
levels, the way a product design studio works, one agent turn per level.

Why (R400, round 1 of the launch eval, 2026-10-20): in one 60-minute turn
the agent built 2 of 8 showcase products. It deliberated 9-20 min before
its first write, wrote 300-600 lines at once, and spent the rest of the
hour on a body that never hollowed or split (toy car: 39 of 40 previews
failed). A level is small enough to end on a passing build, and the next
level starts from that build - a failure costs one level, never the
product.

The levels follow the studio process (brief and volume model, packaging,
surfacing, engineering for manufacture, hardware integration, detail
design, colour / material / finish, refinement, design freeze) in the
order the user asked for. Each has a checklist and a GATE: the review that
must pass before the level ends.

The user's own request is LEVEL 1 (its checklist is in the system prompt);
Atelier sends levels 2..N as messages ending with TURN_TAIL once the
previous level built cleanly. The level state lives in the workspace
marker MARKER, so the panel and the eval harness drive the same ladder.

Pure python: no FreeCAD import (like atech_fit), so the prompt builder,
the panel, the eval harness and the unit tests can all read it.
"""
import json
import os

#: The workspace file that holds the ladder's state (read-only to the agent).
MARKER = ".atech_levels.json"

#: The line every level message ends with (is_level_turn).
TURN_TAIL = ("End this level on a passing ./check, reply in two or three "
             "lines, and stop.")

#: Minutes a level is planned to take, and the minute past which nothing
#: new starts (./check's TURN CLOCK restarts with every turn).
LEVEL_MIN, LEVEL_STOP = 8, 15
LEVEL1_MIN = 12

#: R433: the seeded ladder's budget. A seeded model.py already passes
#: ./check, so LEVEL 1 restyles numbers instead of building the volume
#: (about 10 min, not 12) and every level stops adding at the same minute.
SEEDED_LEVEL1_MIN, SEEDED_LEVEL_MIN, SEEDED_LEVEL_STOP = 10, 8, 15

#: (title, the studio phase it is, checklist, gate). The checklists name
#: kit calls (cad.*, ap.*) the kit really has; {details}, {exterior},
#: {flaws} and {brief_lines} are filled by level_text().
LEVELS = (
    ("Brief, references and the rough volume",
     "concept and volume model",
     "- DESIGN BRIEF to the user first, at most {brief_lines} lines besides "
     "the detail list:\n"
     "  what it is and who it is for; its character in three words; two or "
     "three real\n"
     "  products it must stand next to on a shop shelf; its silhouette, "
     "proportions and\n"
     "  stance, from what it is and the user's words; the overall size in "
     "mm; the part\n"
     "  split; the colour and material per part; and the numbered\n"
     "  DETAIL LIST - at least {details} items, at least {exterior} on the "
     "outside, the\n"
     "  hero feature first. Decide, do not deliberate.\n"
     "- intent.json with the user's numbers.\n"
     "- model.py: the VOLUME MODEL - the product's own masses at their final "
     "proportions\n"
     "  (body, cabin or head, wheels, base, arm, shade), drawn from the "
     "product, never\n"
     "  from the board's box. No hollowing and no openings yet.\n"
     "- Squint test: look at the front, side and top of the review sheet - "
     "each must\n"
     "  read as the product from its outline alone, never as a box or a "
     "slab.",
     "the build passes and its silhouette reads as the product from the "
     "front, the side and the top, at the size in the brief."),
    ("Package the Atech board inside",
     "packaging",
     "- Set board.Placement from the preset that serves the silhouette "
     "(FLAT for low,\n"
     "  long products, UPRIGHT for tall ones), then seat or cable every "
     "module the brief\n"
     "  names at its place: controls under the hands, lights, sensors and "
     "the screen\n"
     "  where the eyes need them, USB-C where a real product's port would "
     "be.\n"
     "- cad.bound_of(board, *modules, *ribbons) plus clearance and wall is "
     "the floor:\n"
     "  grow or reshape the volume until all of it fits inside - never "
     "shrink the\n"
     "  silhouette onto the board's box.",
     "every piece of hardware lies inside the volume with clearance and wall "
     "to spare on every side, and the level 1 silhouette still holds."),
    ("Shape the surfaces and smooth the edges",
     "form development and surfacing",
     "- Turn the blocks into designed surfaces: crowned tops, drafted or "
     "tapered sides,\n"
     "  one clear character line, and the hero's secondary forms (a cabin "
     "narrower than\n"
     "  the body, wheel arches, a head on a neck, grips).\n"
     "- RADIUS HIERARCHY: large radii on the main masses, one smaller "
     "consistent family\n"
     "  on the secondary forms, no sharp visible edge. Fillet the main forms "
     "now,\n"
     "  before any opening is cut (cad.profile_body fillet=, cad.soften).\n"
     "- Robust forms: straight lines and tangent arcs, or a revolve or a "
     "loft of a few\n"
     "  sections - never many-knot splines.",
     "no sharp or faceted visible edge, every main surface has crown or "
     "draft, and the highlights run on without a break."),
    ("Engineer the shell",
     "engineering for manufacture",
     "- Hollow every housing to one uniform wall (cad.hollow with its own "
     "core, or the\n"
     "  forked example's construction for that body).\n"
     "- Split it into parts along a designed break line - a character line "
     "or a\n"
     "  colour change, never an arbitrary height - with a lip (cad.split).\n"
     "- Fasten it like a real product: screw bosses with ribs and matching "
     "holes\n"
     "  (cad.screw_through or cad.screw_boss with cad.screw), the board held "
     "by a pocket\n"
     "  or ledge plus a rib onto its spine. List the parts fitted after the "
     "modules in\n"
     "  intent.json \"fitted_after\".",
     "every housing is hollow with uniform walls, the parts split on a "
     "designed line and are screwed together, and ./check reports no "
     "overlap and no thin wall."),
    ("Integrate the modules, openings and cable routes",
     "hardware integration",
     "- Every module's working face gets its real opening from its measured "
     "box:\n"
     "  cad.opening_for, a key cap with a flange over a button, a lens over "
     "a light, a\n"
     "  hole field over a speaker or microphone, an open aperture in front "
     "of the\n"
     "  distance sensor, the screen's window with a bezel, the USB-C pocket "
     "with the wall\n"
     "  at most 1.5 mm in front of the mouth.\n"
     "- A seat for every module (a pocket, a ledge or a rib), its slide-in "
     "path clear.\n"
     "- CABLE ROUTES: every ribbon runs in a channel or between guide ribs "
     "moulded into\n"
     "  the shell, routed with ap.cable via waypoints, never through a "
     "wall.",
     "every working face is exposed through a fitted opening, every module "
     "is held, every ribbon has its route, and the Atech check passes."),
    ("Add the 3D details",
     "detail design",
     "- Work down the DETAIL LIST, the hero feature first: the features that "
     "make the\n"
     "  product recognisable, in real 3D (a car: tyres with tread, rims with "
     "spokes,\n"
     "  wheel arches, head and tail lights, a grille, bumpers, mirrors, "
     "handles,\n"
     "  recessed windows; a robot: a face, eyes, ears, arms, feet).\n"
     "- A part of another material is its own part: lenses, glass, tyres, "
     "key caps.\n"
     "- One feature per Edit, each in its own `with cad.detail(\"name\"):` "
     "block, ./check\n"
     "  after every Edit that adds a boolean or a fillet.",
     "at least {exterior} exterior detail-list items are in and the product "
     "reads as the named product in a close-up."),
    ("Colour, material and finish",
     "CMF",
     "- Two or three main materials plus accents: a body colour, a contrast "
     "for the\n"
     "  secondary parts, metal or rubber accents, clear or smoked glass and "
     "lenses, and\n"
     "  one signal colour on what the user touches (buttons, the hero "
     "light).\n"
     "- Colour follows parts: where the material changes, the part changes "
     "(a real\n"
     "  product cannot paint a lens). Set each with cad.color / "
     "cad.transparency.",
     "every part has its material, the split reads as intentional (light "
     "against dark, gloss against matte), and the touch points stand out."),
    ("Cut and refine the details",
     "refinement",
     "- Grilles and vents with a real open area, panel lines and a constant "
     "parting-line\n"
     "  reveal, seams, recessed windows, debossed or embossed lettering and "
     "the logo,\n"
     "  texture where hands or the ground touch (knurl, ribs, tread), edge "
     "breaks on\n"
     "  every cut edge.\n"
     "- Then a full review round: Read the review sheet and the close-ups, "
     "write down at\n"
     "  least {flaws} concrete flaws (\"the grille sits 3 mm off the "
     "speaker's centre\")\n"
     "  and fix every one, and every detail ./check reports skipped.",
     "every detail-list item is in, none skipped, and the review finds nothing a design "
     "lead would send back."),
    ("Make it product ready",
     "design freeze",
     "- The release audit, as before tooling: uniform walls, draft on "
     "moulded faces,\n"
     "  every fastener with its boss and hole, 0.2-0.3 mm clearance between "
     "fitted parts,\n"
     "  feet, nothing floating, every module's slide-in path clear, an "
     "assembly order\n"
     "  that works.\n"
     "- A last review against the real products named in the brief: fix "
     "whatever falls\n"
     "  short of them on the shelf.\n"
     "- Then the FINAL REPLY for the user (the full one).",
     "a passing ./check with nothing significant left: the design could go "
     "to tooling."),
)

COUNT = len(LEVELS)

#: R431: the first checklist line of every SEEDED level. Restyling a
#: passing example must never undo what makes it a product.
HERO_RULE = ("- NEVER seal a working opening or drop a lens the hardware "
             "needs (examples/{seed}):\n"
             "  when the form changes, move the opening with its module.")

#: R430: what changes when model.py was seeded (build.seed_model): LEVEL 1
#: RESTYLES the passing example instead of building a volume model, and
#: LEVELS 2-5 verify what the example already has against their GATE
#: instead of building it again. Round 1: rebuilding the shell cost the
#: hour in OCCT hollow / split / fillet failures. {n: (checklist, gate)};
#: LEVELS 6-9 keep their own checklist and gate (after HERO_RULE).
SEEDED = {
    1: ("- DESIGN BRIEF to the user first, at most {brief_lines} lines "
        "besides the detail list:\n"
        "  what it is and who it is for; its character in three words; two "
        "or three real\n"
        "  products it must stand next to on a shop shelf; its silhouette, "
        "proportions and\n"
        "  stance, from what it is and the user's words; the overall size "
        "in mm; the part\n"
        "  split; the colour and material per part; and the numbered\n"
        "  DETAIL LIST - at least {details} items, at least {exterior} on "
        "the outside, the\n"
        "  hero feature first. Decide, do not deliberate.\n"
        "- intent.json with the user's numbers.\n"
        "- model.py already holds examples/{seed}, a build that passes "
        "./check. KEEP its\n"
        "  hardware and fit code: the board placement, modules and cables, "
        "cradle, stops,\n"
        "  openings and fasteners. Its body is not your design: REDESIGN the "
        "silhouette\n"
        "  freely for this request - new side, front and plan outlines, "
        "proportions and\n"
        "  parts - on its construction calls (cad.profile_body, cad.hollow, "
        "cad.split) with\n"
        "  your numbers, and move the hardware where the new form needs it.\n"
        "- Squint test: look at the front, side and top of the review sheet "
        "- each must\n"
        "  read as the requested product from its outline alone, never as a "
        "box or a slab.\n"
        "- End on CHECK PASS.",
        "CHECK PASS; the silhouette reads as the requested product (not the "
        "example, not a box) from the front, side and top; the board held, "
        "the modules retained and open, the USB-C reachable."),
    2: ("- The seed's board, modules and ribbons are already packaged. "
        "Verify against the GATE;\n"
        "  change only what fails it.\n"
        "- A module the brief names that the seed lacks: seat or cable it "
        "at its place\n"
        "  (controls under the hands, lights, sensors and the screen where "
        "the eyes need\n"
        "  them); one the brief drops goes with its opening, seat and "
        "route.\n"
        "- cad.bound_of(board, *modules, *ribbons) plus clearance and wall "
        "is the floor: where\n"
        "  the restyle cut into it, grow the volume back - never shrink the "
        "silhouette onto\n"
        "  the board's box.",
        "every piece of hardware lies inside the volume with clearance and "
        "wall to spare on every side, and the level 1 silhouette still "
        "holds."),
    3: ("- The seed's surfaces are already filleted. Verify against the "
        "GATE; change only\n"
        "  what fails it.\n"
        "- A flat or sharp main surface the restyle left: crown, draft or "
        "round it through the\n"
        "  seed's own outline and fillet numbers in the parameter block - "
        "the openings are\n"
        "  already cut, so a new fillet goes in the body code BEFORE its "
        "cuts, never on the\n"
        "  cut body.\n"
        "- Robust forms: straight lines and tangent arcs, or a revolve or a "
        "loft of a few\n"
        "  sections - never many-knot splines.",
        "no sharp or faceted visible edge, every main surface has crown or "
        "draft, and the highlights run on without a break."),
    4: ("- The seed's housing is already hollow, split and screwed. Verify "
        "against the GATE;\n"
        "  change only what fails it.\n"
        "- A thin wall or an overlap the restyle caused is fixed by its "
        "number (wall,\n"
        "  clearance, boss or split position) in the parameter block - never "
        "by a shell of\n"
        "  your own. A part the restyle added gets its own boss and screw "
        "(cad.screw_through\n"
        "  or cad.screw_boss with cad.screw) and its place in intent.json "
        "\"fitted_after\".",
        "every housing is hollow with uniform walls, the parts split on a "
        "designed line and are screwed together, and ./check reports no "
        "overlap and no thin wall."),
    5: ("- The seed's openings, seats and cable routes are already in. "
        "Verify against the GATE;\n"
        "  change only what fails it.\n"
        "- A module added or moved at LEVEL 2 gets its real opening from "
        "its measured box\n"
        "  (cad.opening_for, a key cap, a lens, a hole field, the open ToF "
        "aperture, the\n"
        "  screen window with a bezel, the USB-C pocket), a seat and an "
        "ap.cable route in a\n"
        "  channel or between guide ribs.\n"
        "- An opening the restyle moved off its module's face moves back "
        "onto it.",
        "every working face is exposed through a fitted opening, every "
        "module is held, every ribbon has its route, and the Atech check "
        "passes."),
}

#: R620 (the user, 2026-10-26: "mix relevant atech modules with the 3D cad
#: and use wires to put things like eyes or motors at different places"):
#: the MODULE PLAN. Before it, level 2 seated or cabled only the modules
#: the brief NAMED, so a product the user described without hardware came
#: out with the seed's modules or none, sitting wherever the ports are.
#: Lines added to a level's checklist and gate when build passes
#: module_plan=True (Atech hardware on, switch "module_plan" not off).
MODULE_PLAN = {
    1: ("\n- MODULE PLAN in the brief, one line per module: its job -> the "
        "Atech module ->\n"
        "  where on the product -> seated on port N, or CABLED from port N "
        "and the route.\n"
        "  Plan what a real product of its kind has, not only what the user "
        "named: eyes\n"
        "  (distance_sensor, or lights / the screen as a face), motors "
        "(dc_motor at the\n"
        "  wheel, arm, head or fan it drives), lights where they shine, "
        "buttons under the\n"
        "  fingers, a speaker or microphone where it is heard, a sensor "
        "where it senses,\n"
        "  usbc for power. A module whose job is at a PLACE on the product "
        "is cabled there\n"
        "  (ap.cable, via waypoints inside the body) unless its seat is "
        "already that place;\n"
        "  where a port happens to sit never moves the eyes or the motor.",
        ""),
    2: ("\n- Seat or cable every module in the MODULE PLAN at its planned "
        "place: each cabled\n"
        "  one at its feature (eyes in the head or nose, a motor at what it "
        "drives), its\n"
        "  ribbon inside the volume. A module you drop leaves the plan with "
        "a reason in the\n"
        "  reply.",
        "; every module in the MODULE PLAN is in place, the cabled ones at "
        "their features"),
}

#: R630: the firmware half of the MODULE PLAN (build.firmware_on - the
#: Atech SDK catalog loads): what each module does, then project.yaml.
FIRMWARE_PLAN = {
    1: ("\n- End each MODULE PLAN line with its firmware job (an SDK method "
        "or event).",
        ""),
    2: ("\n- project.yaml (FIRMWARE) lists every module on its build ports "
        "and its code:\n"
        "  does what the MODULE PLAN says; ./check's FIRMWARE lines are clean "
        "or named\n"
        "  in the reply.",
        ""),
}

#: R432/R600: the levels whose checklist carries the archetype's design
#: note. R600 (the user, 2026-10-26: "it overfits too much to be a box
#: now"): an advisory note in the checklist, never a GATE - no level gates
#: on archetype minimums.
ARCHETYPE_LEVELS = (1, 6)

#: R600: how a level's checklist names the archetype (build.archetype_note).
ARCHETYPE_NOTE = "\n- Design note (advisory, never a gate): %s"

#: R433: the seeded level's time line.
SEEDED_BUDGET = ("\nTIME: about %d min for this level; past %d min on the "
                 "TURN CLOCK add nothing new.")


def _values(details, exterior, flaws, brief_lines, seed=None):
    return {"details": details, "exterior": exterior, "flaws": flaws,
            "brief_lines": brief_lines, "seed": seed or "the seed"}


def budget(n, seed=None):
    """R433: (planned minutes, stop minute) for LEVEL n."""
    if seed:
        return (SEEDED_LEVEL1_MIN if n == 1 else SEEDED_LEVEL_MIN,
                SEEDED_LEVEL_STOP)
    return (LEVEL1_MIN if n == 1 else LEVEL_MIN, LEVEL_STOP)


def level_text(n, details=25, exterior=15, flaws=5, brief_lines=25,
               seed=None, archetype=None, module_plan=False, firmware=False):
    """LEVEL n's block: its title, checklist and gate (1-based).

    R430: `seed` (the example model.py was seeded from) gives the seeded
    wording - LEVEL 1 restyles, LEVELS 2-5 verify, every checklist starts
    with HERO_RULE (R431) and a TIME line ends it (R433). Without a seed the
    text is exactly the unseeded ladder's. R432: `archetype` (a line from
    build.archetype_note) is an advisory checklist line of ARCHETYPE_LEVELS
    (R600: never part of the GATE). R620: `module_plan` adds MODULE_PLAN's
    lines to LEVELS 1 and 2; without it the text is unchanged. R630:
    `firmware` (with module_plan) adds FIRMWARE_PLAN's lines after them."""
    title, phase, checklist, gate = LEVELS[n - 1]
    v = _values(details, exterior, flaws, brief_lines, seed)
    if seed:
        checklist, gate = SEEDED.get(n, (checklist, gate))
        checklist = HERO_RULE + "\n" + checklist
    checklist = checklist.format(**v)
    if module_plan and n in MODULE_PLAN:
        checklist += MODULE_PLAN[n][0]
        gate += MODULE_PLAN[n][1]
        if firmware and n in FIRMWARE_PLAN:
            checklist += FIRMWARE_PLAN[n][0]
            gate += FIRMWARE_PLAN[n][1]
    if archetype and n in ARCHETYPE_LEVELS:
        checklist += ARCHETYPE_NOTE % archetype
    text = "LEVEL %d of %d - %s (%s)\n%s\nGATE: %s" % (
        n, COUNT, title.upper(), phase, checklist, gate.format(**v))
    if seed:
        text += SEEDED_BUDGET % budget(n, seed)
    return text


def overview():
    """One line per level, for the system prompt."""
    return "\n".join("  %d. %s (%s)" % (i + 1, t, p)
                     for i, (t, p, _c, _g) in enumerate(LEVELS))


def level_message(n, seed=None, **kw):
    """The message Atelier sends to start LEVEL n (n >= 2); `seed` and the
    other keywords go to level_text (R430)."""
    return "%s\n%s" % (level_text(n, seed=seed, **kw), TURN_TAIL)


def is_level_turn(request):
    """True when `request` is Atelier's level message, not the user's."""
    return isinstance(request, str) and request.rstrip().endswith(TURN_TAIL)


# ------------------------------------------------------------------ marker
def _path(workspace):
    return os.path.join(workspace, MARKER)


def read(workspace):
    """The ladder's state {"level": n, "count": N, "seed": name or None}
    (plus "archetype": the design note, when write() was given one - R432),
    or None when no ladder runs in `workspace` (or the marker is not a
    regular file the panel wrote)."""
    p = _path(workspace)
    if not workspace or os.path.islink(p) or not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            state = json.load(fh)
        level = int(state["level"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not 1 <= level <= COUNT:
        return None
    state["level"] = level
    state["count"] = COUNT
    return state


def write(workspace, level, seed=None, archetype=None):
    """Record LEVEL `level` as the running one (read-only to the agent;
    a link planted at the marker is removed, never followed). R432:
    `archetype` (build.archetype_note's line) is kept for the levels that
    show it; the key is only written when there is one."""
    p = _path(workspace)
    if os.path.islink(p):
        os.unlink(p)
    elif os.path.exists(p):
        os.chmod(p, 0o644)
    tmp = p + ".tmp"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        state = {"level": int(level), "count": COUNT, "seed": seed}
        if archetype:
            state["archetype"] = str(archetype)
        json.dump(state, fh)
        os.fchmod(fh.fileno(), 0o444)
    os.replace(tmp, p)


def clear(workspace):
    """End the ladder (the user took over with a message of their own)."""
    p = _path(workspace)
    try:
        if os.path.lexists(p):
            os.unlink(p)
    except OSError:
        pass


def advance(workspace, **kw):
    """After LEVEL n built cleanly: record n + 1 and return its message, or
    None when no ladder runs or the last level is done (the marker then
    goes, so a later turn is an ordinary one)."""
    state = read(workspace)
    if state is None:
        return None
    nxt = state["level"] + 1
    if nxt > COUNT:
        clear(workspace)
        return None
    # R430/R432: the seed and the archetype line ride along to every level
    # (a caller's own keyword wins).
    seed, arch = state.get("seed"), state.get("archetype")
    write(workspace, nxt, seed, arch)
    kw.setdefault("seed", seed)
    kw.setdefault("archetype", arch if isinstance(arch, str) else None)
    return level_message(nxt, **kw)
