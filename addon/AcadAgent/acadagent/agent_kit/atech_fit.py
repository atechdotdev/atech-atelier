"""atech_fit - the one source of the Atech print-fit numbers (plan T1).

Everything the fit-first prompt, the kit fit calls (ac.stop_walls,
cad.usbc_port, ac.saddle, ac.hold_down, ac.cradle) and ./check's FIT lines
need is here, so none of them types a fit number of its own:

    FIT          {key: (value, tag, note)}  every number, tagged
    TABLE        {key: "A".."D"}            which prompt table shows it
    KIT_APPLIED  keys a kit call applies itself (left out of the tables;
                 the rules still name them inline through prompt_values())
    STAGES       minute each turn stage starts (./check's TURN CLOCK)
    FORKS        [(request-words regex, example name)], first match wins
    PRESETS      board orientations (plan 4.1 step 1)
    value(key)   the bare value
    text(key)    the value as the prompt prints it ("13.5 x 7.5")
    prompt_values()  {key: text(key)} for str.format of rules R6-R12
    fork_for(request)  the example a new product is seeded from
    render_tables()    prompt text for FIT tables A-D

Tags (plan 4.2):
    CAD  measured from the vendor meshes (frame-2.glb, the module STLs;
         scratchpad fitplan/MEASUREMENTS.md and mods.out)
    EX   proven in a passing example
    STD  from a published standard
    A    an assumption for FDM (0.4 nozzle, 0.2 layer) to confirm with the
         fit coupon (T0); ./check lists the A values a build used
A tag may join several with "/" ("CAD/A": the hardware number is
measured, the clearance on it is assumed).

Board datums are the MEASURED ones (GLB, 2026-10-20), not the plan's draft
row: plan corner radius r 3.0 (ATECH_PRODUCTS.md said ~1), top edge rounded
about r 0.8, 7.00 thick (the STL says 6.49: open item U1), four 3.2 holes
under the spine (ATECH_PRODUCTS.md said none; probably unusable, U12), PCB
1.6 thick, spine plateau at y 4.5 over x 21-39, z 21-99 with a 1 mm 45
degree chamfer down to y 3.5 at x 20/40, z 20/100.

BOARD FIRST (R281, the CAD + electronics mode). hw_mode.electronics() turns
on panel._show_board_first: the real 14-port board is put in the document
and shown BEFORE the agent writes anything, and the CAD is built around it.
So a seeded fork (T5) must never make a second board: model.py takes the
existing one with ap.board_object(doc) (it finds the board by AtechRole,
then by label, and creates one only when none exists) and then sets that
board's Placement for the fork's preset (PRESETS) before any ap.seat.
BOARD_FIRST below records this for the seeding code and its tests.

Pure python: no FreeCAD import, so the prompt builder, the eval harness and
the unit tests can read it anywhere.
"""
import re

#: In CAD + electronics mode the board is already in the document when the
#: agent starts (panel._show_board_first). Seeded forks reuse it through
#: ap.board_object(doc) and only set its Placement for the preset.
BOARD_FIRST = True

TAGS = ("CAD", "EX", "STD", "A")

# --------------------------------------------------------------------- FIT
# value: a number, a tuple of numbers (sizes "a x b", ranges lo..hi are
# named *_x/_y/_z or *_range), a dict, or a string.
FIT = {
    # ---- A. hardware datums (board frame: X 0-60 across, Y up with the
    # PCB top at y 0, Z 0-120 along). Source: MEASUREMENTS.md table A.
    "board_x": ((0.013, 59.988), "CAD", "board outline across (carrier frame)"),
    "board_z": ((0.013, 119.988), "CAD", "board outline along"),
    "board_y": ((-2.50, 4.50), "CAD", "underside to spine top"),
    "board_thickness": (7.00, "CAD",
                        "GLB 7.00 (y -2.50..+4.50); the STL says 6.49 "
                        "(top 3.99): conflict, caliper a board (U1)"),
    "board_corner_r": (3.0, "CAD", "plan corner radius, all four corners"),
    "board_edge_r": (0.8, "CAD", "top outer edge rounding (bottom about 0.6)"),
    "board_edge_r_bottom": (0.6, "CAD", "bottom outer edge rounding"),
    "board_underside_y": (-2.50, "CAD",
                          "flat over the whole footprint, nothing below it"),
    "pcb_thickness": (1.60, "CAD", "PCB y -1.60..0, inset 1.0 in the carrier"),
    "pcb_corner_r": (2.0, "CAD", "PCB plan corner radius"),
    "carrier_rim": (0.9, "CAD",
                    "tray rim 0.85-1.0 wide, flush with the PCB top: "
                    "the surface a ledge may bear on"),
    "board_hole_d": (3.2, "CAD", "PCB hole diameter"),
    "board_holes": (((25.0, 25.0), (35.0, 25.0), (25.0, 95.0), (35.0, 95.0)),
                    "CAD",
                    "four PCB holes (x, z), 10 x 70 pattern, UNDER the "
                    "spine, tray solid below: not usable for mounting (U12)"),
    "spine_top_y": (4.50, "CAD", "spine plateau height (STL says 3.85)"),
    "spine_plateau_x": ((21.0, 39.0), "CAD", "flat spine top across"),
    "spine_plateau_z": ((21.0, 99.0), "CAD", "flat spine top along"),
    "spine_frame_x": ((20.0, 40.0), "CAD", "spine footprint across"),
    "spine_frame_z": ((20.0, 100.0), "CAD", "spine footprint along"),
    "spine_chamfer": (1.0, "CAD", "45 deg chamfer, y 3.5 to 4.5"),
    "spine_ledge_y": (2.50, "CAD",
                      "ledges x 16.85-20 / 40-43.2 and z 16.85-20 / "
                      "100-103.2 beside the port rows"),
    "module_proud": ((0.37, 0.67), "CAD",
                     "seated modules stand this far past the board edge"),
    "module_h": (9.54, "CAD", "module case top above the PCB top"),
    "module_size": (19.5, "CAD", "1-connector module, square"),
    "two_connector": ((39.5, 19.5), "CAD",
                      "screen and microphone; speaker 40 x 40"),
    "speaker_box": ((40.0, 40.0, 20.2), "CAD",
                    "20.6 past the board edge, 20.2 tall"),
    "speaker_overhang": (20.6, "CAD", "speaker past the board edge"),
    "motor_overhang": (20.4, "CAD",
                       "dc_motor gearbox past the edge (box 39.5 long)"),
    "motor_shaft": ((3.0, 8.8), "CAD",
                    "dc_motor shaft d 3.0, tip 8.8 past the box "
                    "(29.2 past the board edge)"),
    "usbc_mouth": ((10.0, 3.5), "CAD",
                   "receptacle, 8.26 deep, 0.25 proud; position from "
                   "atech_geom.socket_face"),
    "ribbon": ((14.0, 0.6), "CAD",
               "stand-in ribbon; straight 3.7 board end, 14.5 module end"),
    "slide_travel": (19.12, "CAD", "slide-in travel (speaker 19.4)"),

    # ---- B. working faces (plan 4.2 B); value = the numbers a kit call
    # or ./check reads, note = the rule the prompt prints.
    "face_screen": ({"active": (25.6, 13.5), "window_min": (27.0, 15.0),
                     "bezel": (0.8, 1.5)}, "CAD/EX",
                    "active 25.6 x 13.5; window >= 27 x 15; bezel recess "
                    "0.8-1.5"),
    "face_distance_sensor": ({"aperture_min": (10.0, 6.0),
                              "per_2mm_wall": 1.0, "chamfer_deg": 15.0},
                             "CAD/A",
                             "aperture >= 10 x 6 + 1.0/side per 2 of wall, "
                             "or 15 deg chamfer; no glass"),
    "face_light": ({"field": (17.0, 17.0), "lens_gap": 0.4}, "CAD/A",
                   "LED field 17 x 17 open, or a separate lens 0.4 off"),
    "face_button": ({"cap_clear": 0.3, "cap_lift": 0.2}, "A",
                    "separate key cap in cap + 0.3; rests 0.2 over the "
                    "actuator; travel unknown"),
    "face_speaker": ({"open_min": 0.40, "seal_gap": 0.2, "air": 1.5},
                     "EX/A",
                     "grille over the cone >= 40 % open; seal ring 0.2 "
                     "off; >= 1.5 air"),
    "face_microphone": ({"open_min": 0.30, "port_d_min": 1.0,
                         "port_len_max": 2.0, "gasket": 0.2}, "A",
                        "grille over the whole face >= 30 % open (port "
                        "position unknown)"),
    "face_temp_humidity": ({"vent_faces": 2, "vent_mm2": 30.0}, "A",
                           "own chamber at the outer wall; vents on 2 "
                           "faces >= 30 mm2 each"),
    "face_orientation": ({}, "A", "no opening; mount rigidly"),
    "face_dc_motor": ({"bearing_d": 3.3}, "CAD/A",
                      "shaft through a 3.3 bearing hole; saddle under the "
                      "gearbox"),
    # ./check FIT faces thresholds (share of rays that reach air).
    "face_open": ({"light": 0.60, "button": 0.60, "speaker": 0.25,
                   "microphone": 0.25, "screen": 1.00}, "A",
                  "FIT faces pass share: light/button 60 %, sound 25 %, "
                  "screen 100 % of the active area"),

    # ---- C. FDM fit classes (per side; "Z" = the part's own print Z).
    "slide": (0.30, "A", "cavity round hardware, corridors, cabled pockets"),
    "fence": (0.25, "A", "fence to board frame edge"),
    "fence_top_mod": (-0.3, "CAD", "fence top y on an edge with modules"),
    "rib": (1.2, "A", "fence and rib width"),
    "stop": (0.20, "A", "stop wall or land to a module's outboard face"),
    "backlash_max": (0.50, "CAD/A",
                     "stop + 0.30 proud spread; about 2.1 of pin "
                     "engagement left"),
    "preload": (0.10, "A", "hold-down rib modelled into the spine"),
    "preload_tip": (0.8, "A", "hold-down rib tip width"),
    "preload_max": (0.30, "A", "most preload overlap ./check allows"),
    "layer": (0.2, "A", "Z gaps are 0 or at least this"),
    "hole_z": (0.2, "A", "added in Z to round holes with a horizontal axis"),
    "press": (0.00, "A", "printed pin in printed hole, as modelled"),
    "rotate": (0.25, "A", "radial, printed pin turning in a hole"),
    "lip_loose": (0.20, "A", "lid lip, loose"),
    "lip_friction": (0.15, "A", "lid lip, friction"),
    "bearing_d3": (3.3, "A", "hole for a 3 mm shaft"),
    "dbore_d3": ((3.10, 2.60), "CAD/A",
                 "hub on the dc_motor shaft: bore / flat"),
    "pilot": ({"M2": 1.7, "M2.5": 2.1, "M3": 2.5}, "A",
              "thread-forming pilot, depth >= 2.5 d"),
    "insert": ({"M2": 3.2, "M2.5": 3.6, "M3": 4.0}, "A",
               "heat-set insert hole, depth insert + 0.5"),
    "boss_od_rule": ("max(2.5d, 5.0)", "A", "screw boss outer diameter"),
    "wall": (2.0, "EX", "wall thickness"),
    "wall_min": (1.2, "A", "3 perimeters at 0.4"),
    "corner_keepout": (5.0, "EX",
                       "hardware corner to a rounded inner wall (round-1 "
                       "lesson)"),
    "air_speaker": (1.5, "EX/A", "air over a speaker"),
    "pad_min": ((6.0, 6.0), "A", "pad under the board behind a button"),
    "pin_min": (5.0, "A", "thinnest horizontal printed pin"),
    "snap_strain": ({"PLA": 0.015, "PETG": 0.03}, "A",
                    "snap_fit_pair max_strain"),
    "material": ("PLA", "A", "default material"),
    "bed_face_min": (0.30, "A", "FIT bed: flat face share of the footprint"),
    "desk_tol": (0.05, "A", "FIT desk: product minimum z = 0 within this"),
    "retain_cover": (0.30, "A", "FIT retain: share of the outboard face "
                                "covered within stop +/- 0.1"),

    # ---- D. USB-C and cables.
    "usbc_open": ((13.5, 7.5), "STD/A",
                  "full wall depth; clears a ~12.35 x 6.5 USB-IF overmold"),
    "usbc_r": (3.25, "STD/A", "usbc_open corner radius"),
    "usbc_keepout": ((13.5, 7.5, 25.0), "A", "kept clear outward"),
    "usbc_land": ((1.5, 0.2), "CAD/A",
                  "lands over/under the receptacle: width, gap"),
    "ribbon_channel": (16.0, "A", "ribbon 14 + 1 per side"),
    "ribbon_gap": (0.5, "A", "ribbon to any part"),
    "fold_allow": (1.8, "A", "per 45 deg fold, 3 x ribbon thickness"),
    "ribbon_bend_r": (3.0, "A", "minimum bend (FFC datasheet pending)"),
    "ribbon_clamp": (0.7, "A", "clamp rib gap over the ribbon, within 5 "
                               "of each plug"),
}

#: Which prompt table shows a key ("A".."D"); a key not here is for the kit
#: or ./check only.
TABLE = {}
for _k in ("board_x", "board_z", "board_y", "board_thickness",
           "board_corner_r", "board_edge_r", "board_underside_y",
           "pcb_thickness", "board_holes", "spine_top_y", "spine_plateau_x",
           "spine_plateau_z", "spine_ledge_y", "module_proud", "module_h",
           "two_connector", "speaker_box", "motor_overhang", "motor_shaft",
           "usbc_mouth", "ribbon"):
    TABLE[_k] = "A"
for _k in ("face_screen", "face_distance_sensor", "face_light",
           "face_button", "face_speaker", "face_microphone",
           "face_temp_humidity", "face_orientation", "face_dc_motor"):
    TABLE[_k] = "B"
for _k in ("slide", "fence", "fence_top_mod", "rib", "stop", "backlash_max",
           "preload", "preload_tip", "layer", "hole_z", "press", "rotate",
           "lip_loose", "lip_friction", "bearing_d3", "dbore_d3", "pilot",
           "insert", "boss_od_rule", "wall", "wall_min", "corner_keepout",
           "air_speaker", "pad_min", "pin_min", "snap_strain", "material"):
    TABLE[_k] = "C"
for _k in ("usbc_open", "usbc_r", "usbc_keepout", "usbc_land",
           "ribbon_channel", "ribbon_gap", "fold_allow", "ribbon_bend_r",
           "ribbon_clamp"):
    TABLE[_k] = "D"
del _k

#: Keys a kit call applies itself (plan T3): the rules still quote them
#: inline, but the tables leave them out to save prompt length.
KIT_APPLIED = frozenset((
    "fence", "fence_top_mod", "rib",                 # ac.cradle
    "preload", "preload_tip",                        # ac.hold_down
    "usbc_r", "usbc_keepout", "usbc_land",           # cad.usbc_port
    "pilot", "insert", "boss_od_rule",               # ad.screw_boss
    "dbore_d3",                                      # cad.wheel(flat=)
    "lip_friction",                                  # cad.split default
))

#: The {placeholders} of prompt rules R6-R12 and procedure 4.1 (plan 3.4).
RULE_KEYS = (
    "stop", "slide", "usbc_open", "usbc_r", "usbc_keepout", "ribbon_gap",
    "ribbon_channel", "fold_allow", "ribbon_bend_r", "ribbon_clamp", "layer",
    "hole_z", "pin_min", "material", "corner_keepout", "wall", "wall_min",
    "air_speaker", "fence", "rib", "fence_top_mod", "pad_min", "preload_tip",
    "preload", "backlash_max", "lip_loose", "boss_od_rule", "snap_strain",
)

# ------------------------------------------------------------------ stages
#: Minute of the turn each stage starts (assumed; retune from Phase 0).
STAGES = {"A": 0, "B": 12, "C": 28, "STOP": 48}


def stage_at(minutes):
    """The stage a turn is in after `minutes`."""
    cur = "A"
    for name, start in sorted(STAGES.items(), key=lambda kv: kv[1]):
        if minutes >= start:
            cur = name
    return cur


# ------------------------------------------------------------------- forks
#: (request-words regex, example name); the first match wins (plan 5).
# R414: each showcase archetype forks its own example (ATECH_PRODUCTS.md
# section 0A says the same). First match wins: the tank before the car
# words, the robot before the clock / fan / weather / speaker words ("a
# speaker robot" is a robot), the fan before the lamp words ("a desk fan
# with lights" is a fan).
FORKS = [
    # R803: the five Atech-hardware examples, first: a balancing robot and
    # a robot arm before desk_robot's "robot", a motion sensor light before
    # the lamp's "light" ("a night light" stays the bedside lamp), a rover
    # before the car words
    (r'\b(self[ -]?balanc\w*|balanc(e|ing)[ -]?(ro)?bots?|segways?|inverted[ -]pendulums?)\b', 'balance_bot'),
    (r'\b(robot(ic)?[ -]?arms?|arm[ -]?(docks?|bases?|mounts?|controllers?)|so[ -]?101|so[ -]?arm\w*)\b', 'arm_dock'),
    (r'\b(motion[ -]?(sensing|sensors?|activated|detecting|triggered|lights?|lamps?)|pir)\b', 'motion_light'),
    (r'\b(air[ -]?(quality|monitors?|sensors?|meters?)|co2|carbon dioxide)\b', 'air_monitor'),
    (r'\b(rovers?|4wd|crawlers?|all[ -]terrain)\b', 'rover'),
    # R802: the ten starter examples, first (their words are specific)
    (r'\b(planters?|(?:plant|flower) ?pots?|flowerpots?|cachepots?|herb gardens?)\b', 'smart_planter'),
    (r'\b(feeders?|kibble|feeding stations?)\b|\b(?:pet|cat|dog) food\b', 'pet_feeder'),
    (r'\b(door ?bells?|intercoms?|entry ?phones?)\b', 'video_doorbell'),
    (r'\b(arcades?|bartops?)\b', 'mini_arcade'),
    (r'\b(music[ -]?box(es)?|juke[ -]?box(es)?|record[ -]?players?)\b', 'music_box'),
    (r'\b(parking|garage)\b', 'parking_sensor'),
    (r'\b(organi[sz]ers?|pen(cil)? ?(holders?|cups?)|desk ?tid(y|ies)|(desk )?cadd(y|ies)|stationery)\b', 'desk_organizer'),
    (r'\b(photo ?frames?|picture ?frames?|digital (photo |picture )?frames?)\b', 'photo_frame'),
    (r'\b(metronomes?|tempo|bpm)\b', 'metronome'),
    (r'\b(macro[ -]?pads?|stream[ -]?decks?|keypads?|keyboards?)\b', 'macro_pad'),
    (r"\btanks?\b", "rc_tank"),
    (r"\b(cars?|vehicles?|trucks?)\b", "toy_car"),
    (r"\b(robots?|desk[ -]?pets?)\b", "desk_robot"),
    (r"\b(clocks?|alarms?|timers?)\b", "alarm_clock"),
    (r"\bfans?\b", "desk_fan"),
    (r"\b(weather|thermometers?|barometers?|stations?)\b", "weather_station"),
    (r"\bspeakers?\b", "smart_speaker"),
    (r"\b(lamps?|lights?)\b", "bedside_lamp"),
    (r"\b(consoles?|games?|gaming)\b", "handheld_console"),
]
DEFAULT_FORK = "atech_case"


def fork_for(request):
    """The example a new product is seeded from."""
    text = (request or "").lower()
    for pattern, name in FORKS:
        if re.search(pattern, text):
            return name
    return DEFAULT_FORK


#: Board orientations (plan 4.1 step 1). rotation: (axis, degrees), or None
#: when the API card gives it. Set on the board ap.board_object(doc) returns.
PRESETS = {
    "FLAT": {"rotation": ((1, 0, 0), 90), "faces": "+Z", "mode": "drop_in"},
    "UPRIGHT_FRONT": {"rotation": ((0, 0, 1), 180), "faces": "-Y",
                      "mode": "slide"},
    "LANDSCAPE_UP": {"rotation": None, "faces": "-Y", "mode": "slide"},
    "LANDSCAPE_FRONT": {"rotation": None, "faces": "-Y", "mode": "slide"},
}


# ---------------------------------------------------------------- reading
def value(key):
    """The bare value of FIT[key]."""
    try:
        return FIT[key][0]
    except KeyError:
        raise KeyError("atech_fit has no %r (keys: %s)"
                       % (key, ", ".join(sorted(FIT))))


#: Keys whose 2-tuple value is a lo..hi range, not a size.
RANGE_KEYS = frozenset(("board_x", "board_y", "board_z", "spine_plateau_x",
                        "spine_plateau_z", "spine_frame_x", "spine_frame_z",
                        "module_proud"))


def _num(x):
    return ("%.3f" % x).rstrip("0").rstrip(".") if isinstance(x, float) \
        else str(x)


def _fmt(v, key=None):
    if isinstance(v, dict):
        return ", ".join("%s %s" % (k, _fmt(x)) for k, x in v.items())
    if isinstance(v, tuple):
        if v and all(isinstance(x, tuple) for x in v):
            return " ".join("(%s)" % ",".join(_num(y) for y in x) for x in v)
        return ("..." if key in RANGE_KEYS else " x ").join(
            _num(x) for x in v).replace("...", "..")
    return _num(v)


def text(key):
    """FIT[key]'s value as the prompt prints it."""
    return _fmt(value(key), key)


def prompt_values():
    """{key: text} for str.format of the rule texts."""
    return {k: text(k) for k in FIT}


_TITLES = {
    "A": "A. Hardware datums (CAD, board frame mm; PCB top y 0)",
    "B": "B. Working faces",
    "C": "C. FDM fits (per side)",
    "D": "D. USB-C and cables",
}

#: Table A's line for a key, when FIT's note is longer than the prompt
#: needs (the note stays the full record).
_SHORT_A = {
    "board_x": "", "board_z": "", "board_y": "underside..spine top",
    "board_thickness": "GLB; STL says 6.49, unconfirmed",
    "board_corner_r": "plan corners", "board_edge_r": "top edge",
    "board_underside_y": "flat, nothing below",
    "pcb_thickness": "",
    "board_holes": "d 3.2 (x,z), under the spine: not for mounting",
    "spine_top_y": "spine top", "spine_plateau_x": "flat top",
    "spine_plateau_z": "flat top",
    "spine_ledge_y": "ledges beside the port rows, x 16.85..43.2",
    "module_proud": "seated module past the board edge",
    "module_h": "module top", "two_connector": "screen, microphone",
    "speaker_box": "20.6 past the edge",
    "motor_overhang": "gearbox past the edge",
    "motor_shaft": "shaft d, tip past the gearbox",
    "usbc_mouth": "receptacle, 0.25 proud",
    "ribbon": "stand-in; straight 3.7 / 14.5",
}


def _shown(table):
    return [k for k, t in TABLE.items() if t == table and k not in KIT_APPLIED]


def render_tables():
    """The FIT NUMBERS prompt section: tables A-D, without KIT_APPLIED keys.
    A: value and a short fact; B: the rule; C, D: key value(tag) runs."""
    out = ["FIT NUMBERS. Tags: CAD measured, EX example, STD standard, "
           "A assumed (test on the first print)."]
    out.append(_TITLES["A"])
    for k in _shown("A"):
        val, tag, note = FIT[k]
        short = _SHORT_A.get(k, note)
        out.append("- %s %s%s" % (k, _fmt(val, k),
                                  (": " + short) if short else ""))
    out.append(_TITLES["B"])
    for k in _shown("B"):
        val, tag, note = FIT[k]
        out.append("- %s: %s (%s)" % (k[len("face_"):], note, tag))
    for table in "CD":
        out.append(_TITLES[table])
        out.append("; ".join("%s %s (%s)" % (k, _fmt(FIT[k][0], k), FIT[k][1])
                             for k in _shown(table)))
    return "\n".join(out)
