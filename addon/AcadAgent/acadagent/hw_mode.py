"""hw_mode - what the agent builds: CAD only, or CAD + Atech electronics
(R280).

The sidebar's switch ("Only CAD | CAD + electronics") sets it; every chat
turn reads it when its system prompt is built (build.board_default), so a
change applies from the next message on.

  electronics  the default: a request with no size ("I want a car") is built
               as a real product around the Atech board and its modules,
               custom-fitted (build.py ATECH BOARD BY DEFAULT).
  cad_only     plain CAD: no board, no modules, no cables are added. Atech
               objects already in the document stay the user's and are
               still respected; a request that names Atech hardware still
               gets the Atech section (wants_atech), because the user asked.

No Qt and no FreeCAD here, so it is testable anywhere.
"""
import os

KEY = "agent_hardware"
ENV = "ATECH_HARDWARE_MODE"
ELECTRONICS = "electronics"
CAD_ONLY = "cad_only"
MODES = (CAD_ONLY, ELECTRONICS)          # the switch's order, left to right
LABELS = {CAD_ONLY: "Only CAD", ELECTRONICS: "CAD + electronics"}


def get(cfg=None):
    """The current mode: $ATECH_HARDWARE_MODE when it names one (the eval
    and tests), else the stored setting, else ELECTRONICS."""
    env = (os.environ.get(ENV) or "").strip().lower()
    if env in MODES:
        return env
    if cfg is None:
        try:
            from . import settings      # lazy: settings imports Qt
            cfg = settings.load()
        except Exception:                              # noqa: BLE001
            cfg = {}
    value = str((cfg or {}).get(KEY) or "").strip().lower()
    return value if value in MODES else ELECTRONICS


def set(mode):                                         # noqa: A001
    """Store the mode. Returns True when saved; an unknown mode raises."""
    if mode not in MODES:
        raise ValueError("hardware mode must be one of %s, not %r" % (MODES, mode))
    from . import settings
    return settings.update(**{KEY: mode})


def electronics(cfg=None):
    """True when new designs get Atech electronics by default."""
    return get(cfg) == ELECTRONICS
