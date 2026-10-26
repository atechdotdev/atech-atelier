"""R230-R233: QUALITY MODE, the default agent behaviour (fast mode keeps
the behaviour before R230).

    R230  the mode: settings "agent_quality" ("quality" | "fast"), env
          $ATECH_PROMPT_MODE; build.quality_mode(); the quality prompt
          (design brief, reads, sculpted forms, ./check + review sheet,
          detail list, >= 3 review rounds, fit, final reply, ./check alone);
          the budget/effort defaults (claude_cli.agent_settings), the build
          and ./check timeout (sandbox.default_timeout), the panel's fix and
          stall limits.
    R231  helper_card() lists atech_cad.py, atech_form.py, atech_detail.py
          (each file's __all__, in that order; a missing file is skipped);
          prepare_workspace copies the helper files beside atech_cad.py.
    R232  prepare_workspace copies agent_kit/reference/*.md to <ws>/reference/.
    R233  build._colour applies Transparency (last, and again after a palette
          colour) as well as ShapeColor and DiffuseColor.

System Python, no FreeCAD needed (the stubbed package of test_claude_cli).
The panel's limits are checked from its source here, and through the real
class where PySide6 imports (under freecadcmd).

RUN
    cd addon/AcadAgent/tests && python3 -m unittest test_quality_mode -v
"""
import ast
import os
import re
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_claude_cli import load_acadagent  # noqa: E402

_PKG = load_acadagent("settings", "claude_cli", "sandbox", "build")
settings, cli, sandbox, build = (_PKG.settings, _PKG.claude_cli,
                                 _PKG.sandbox, _PKG.build)
# Never the developer's real settings.json.
_CFG_DIR = tempfile.mkdtemp(prefix="acadagent-cfg-quality-")
settings.CONFIG_DIR = _CFG_DIR
settings.CONFIG_PATH = os.path.join(_CFG_DIR, "settings.json")

PANEL_PY = os.path.join(os.path.dirname(HERE), "acadagent", "panel.py")
WS = "/nonexistent/ws"


def _flat(text):
    return " ".join(text.split())


class _Mode(unittest.TestCase):
    """Each test sets the mode itself; the env and caches are restored."""

    MODE = None

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in
                     ("ATECH_PROMPT_MODE", "ATECH_PROMPT_OFF")}
        os.environ.pop("ATECH_PROMPT_OFF", None)
        if self.MODE:
            os.environ["ATECH_PROMPT_MODE"] = self.MODE
        else:
            os.environ.pop("ATECH_PROMPT_MODE", None)
        self._card, self._helpers = build._CARD, build._HELPERS
        self._saved = []
        try:
            os.remove(settings.CONFIG_PATH)
        except OSError:
            pass

    def tearDown(self):
        for obj, name, val in reversed(self._saved):
            setattr(obj, name, val)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        build._CARD, build._HELPERS = self._card, self._helpers

    def patch(self, obj, name, val):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, val)

    def atech_library(self):
        """The Atech section without FreeCAD: library 'available', a small
        generated card."""
        self.patch(build, "library_available", lambda refresh=False: True)
        self.patch(build, "_generated_card", lambda: "ATECH API CARD (stub)")
        self.patch(build, "assembly_doc", lambda: None)
        build._CARD = None


# ------------------------------------------------------------------ R230
# Every workflow element of the quality prompt, as (name, needle) on the
# whitespace-flattened text. QUALITY_ELEMENTS_IN_ORDER must also appear in
# this order. R600 (the user, 2026-10-26: "it overfits too much to be a box
# now"): DESIGN-FIRST - design the product, then fit, then detail; then the
# workflow (brief -> reads -> first write -> look -> detail -> review).
QUALITY_ELEMENTS = [
    ("design first", "1. DESIGN THE PRODUCT, NOT A CASE"),
    ("silhouette from the product", "Its silhouette, proportions, stance and "
                                    "character come from what it is and from "
                                    "the user's words"),
    ("car words", "A car is long and low with a wheel at each corner"),
    ("draw first", "Draw the product first"),
    ("fit section", "2. FIT"),
    ("detail section", "3. DETAIL AND FINISH"),
    ("brief", "DESIGN BRIEF, as text to the user before any file"),
    ("brief: part split", "the part split and assembly order"),
    ("brief: colours", "colour and material per part"),
    ("brief: detail list", "a numbered DETAIL LIST of about 25 items"),
    ("reads", "READ only what you need"),
    ("reads: example", "the example you start from"),
    ("reads: helper docstring", "a helper's docstring the first time you "
                                "call it"),
    ("first write", "WRITE intent.json, then model.py"),
    ("script path", "model.py is /nonexistent/ws/model.py"),
    ("own forms", "the product's own forms first"),
    ("check + sheet", "LOOK: Read"),
    ("never a box", "If it reads as a box or a slab, redesign the outlines "
                    "now"),
    ("detail one per edit", "DETAIL: the detail list in order, one feature "
                            "per Edit"),
    ("check after booleans", "./check after every Edit that adds a boolean "
                             "or a fillet"),
    ("review rounds", "REVIEW at least 3 rounds"),
    ("flaws", "write down at least 5 concrete flaws"),
    ("stop rule", "Stop when a round finds nothing significant and the "
                  "detail list is in"),
    ("fit: clearance", "Parts that meet keep 0.2-0.3 mm clearance"),
    ("check alone", "never piped or chained"),
    ("never read the checker", "Never read check.py or atech_geom.py: "
                               "./check's output says what fails and how to "
                               "fix it."),
    ("pass is the floor", "A CHECK PASS is the floor, not the goal"),
    ("timeout", "stopped after 180 s"),
    ("final reply", "FINAL REPLY: one short paragraph on the product"),
    ("final reply bullets", "the modules and ports"),
]
# ... and on an Atech turn (the hardware lines).
ATECH_ELEMENTS = [
    ("hardware inside", "The Atech board and modules live INSIDE and never "
                        "set the outer shape"),
    ("pocket only", "the hardware sets a minimum inner pocket, nothing more"),
    ("box is a failure", "A body that is the board's bounding box plus a "
                         "wall, or a slab, is a failure"),
    ("orientation suits the form", "Choose the board orientation to suit the "
                                   "form"),
    ("cable for the design", "Put modules where the design needs them with "
                             "ap.cable"),
    ("brief: hardware", "the hardware: every module, seated or cabled"),
    ("brief: usbc", "the usbc for power"),
]
QUALITY_ELEMENTS_IN_ORDER = ["design first", "fit section", "detail section",
                             "brief", "reads", "first write", "check + sheet",
                             "detail one per edit", "review rounds"]

# The speed rules quality mode replaces (fast mode keeps every one).
FAST_ONLY = [
    "YOUR FIRST TOOL CALL: Write a coarse but complete model.py FIRST",
    "AT MOST 30 LINES",
    "before you read any file",
    "The first CHECK PASS ends the work",
    "no cosmetic edits after a pass",
    "After a CHECK PASS, change model.py again ONLY",
    "After 3 failing ./check runs, stop editing",
    "ONE FEATURE PER EDIT, about 10 lines",
    "Never add a feature the user did not ask for",
    "Final reply: at most two sentences",
    "stopped after 60 s",
    "at least 12 for a vehicle",
]
FAST_ONLY_ATECH = [
    "YOUR FIRST WRITE for an Atech request is this example",
    "at most 2 fix rounds",
    "Make that first Write within a few sentences",
]


def missing_elements(prompt, atech=False):
    """The QUALITY_ELEMENTS (+ ATECH_ELEMENTS) a prompt lacks, plus 'order'
    when the workflow steps are out of order."""
    flat = _flat(prompt)
    miss = [n for n, needle in QUALITY_ELEMENTS + (ATECH_ELEMENTS if atech else [])
            if _flat(needle) not in flat]
    if not miss:
        at = [flat.index(_flat(dict(QUALITY_ELEMENTS)[n]))
              for n in QUALITY_ELEMENTS_IN_ORDER]
        if at != sorted(at):
            miss.append("order")
    return miss


class TestQualityPrompt(_Mode):
    MODE = "quality"

    def prompt(self, **kw):
        return build.system_prompt(WS, **kw)

    def test_R230_every_workflow_element(self):
        for kw in ({"request": "a toy car"}, {"atech": False},
                   {"request": "phone stand with cable hole"}):
            sp = self.prompt(**kw)
            self.assertEqual(missing_elements(sp), [], kw)

    def test_R230_speed_rules_gone(self):
        flat = _flat(self.prompt(request="a toy car"))
        for needle in FAST_ONLY:
            self.assertNotIn(_flat(needle), flat, needle)

    def test_R230_review_sheet_follows_the_kit(self):
        self.patch(build, "kit_writes_review", lambda: True)
        flat = _flat(self.prompt(atech=False))
        for needle in ("Read review.png (./check's six views", "review_inside.png",
                       'REVIEW_CLOSEUPS = ["Label", ...]', "review_<Label>.png"):
            self.assertIn(needle, flat)
        self.patch(build, "kit_writes_review", lambda: False)
        flat = _flat(self.prompt(atech=False))
        self.assertIn("Read check.png", flat)
        self.assertNotIn("review.png", flat)
        self.assertNotIn("REVIEW_CLOSEUPS", flat)

    def test_R230_timeout_in_sync_with_the_sandbox(self):
        self.assertEqual(sandbox.default_timeout(), sandbox.QUALITY_TIMEOUT)
        self.assertEqual(sandbox.QUALITY_TIMEOUT, 180.0)
        flat = _flat(self.prompt(atech=False))
        self.assertIn("stopped after %g s" % sandbox.default_timeout(), flat)
        self.assertIn("(up to %g s)" % sandbox.default_timeout(), flat)

    def test_R230_atech_card_quality_tail(self):
        self.atech_library()
        self.patch(build, "kit_reference", lambda name: True)
        sp = self.prompt(atech=True)
        flat = _flat(sp)
        self.assertEqual(missing_elements(sp, atech=True), [])
        for needle in FAST_ONLY_ATECH:
            self.assertNotIn(_flat(needle), flat, needle)
        # R600: the short quality card
        for needle in ("examples/atech_case.py shows the library calls; never "
                       "copy its box",
                       "never read or grep atech_ports.py",
                       "BOARD PRESETS", "FLAT = Rotation(Vector(1, 0, 0), 90)",
                       "def place_board(",
                       "a usbc for power",
                       "reference/ATECH_PRODUCTS.md: the measured catalogue",
                       "reference/ATECH_PRODUCTS.md (module sizes",
                       "ATECH API CARD (stub)"):
            self.assertIn(_flat(needle), flat, needle)

    def test_R230_hardware_lines_only_on_atech_turns(self):
        flat = _flat(self.prompt(atech=False))
        for name, needle in ATECH_ELEMENTS:
            self.assertNotIn(_flat(needle), flat, name)
        self.assertIn("what it must hold, fit or carry", flat)

    def test_R232_products_named_only_when_the_kit_ships_it(self):
        self.atech_library()
        self.patch(build, "kit_reference", lambda name: False)
        self.assertNotIn("ATECH_PRODUCTS.md", self.prompt(atech=True))

    def test_R230_mode_switch_rebuilds_the_atech_card(self):
        self.atech_library()
        q = build._api_card()
        os.environ["ATECH_PROMPT_MODE"] = "fast"
        f = build._api_card()
        self.assertIn("BOARD PRESETS", q)
        self.assertNotIn("YOUR FIRST WRITE", q)
        self.assertIn("YOUR FIRST WRITE", f)
        self.assertNotIn("BOARD PRESETS", f)

    def test_R230_sabotage_a_missing_element_is_caught(self):
        # Sabotage: the review-round step taken out of the template (R400:
        # THE WORKFLOW is its own text, QUALITY_WORKFLOW).
        self.patch(build, "QUALITY_WORKFLOW", build.QUALITY_WORKFLOW.replace(
            "6. REVIEW at least {reviews} rounds:", "6."))
        self.assertIn("review rounds", missing_elements(self.prompt(atech=False)))
        # Sabotage: the detail floor back at fast mode's 12.
        self.patch(build, "QUALITY_DETAILS", 12)
        self.assertIn("brief: detail list",
                      missing_elements(self.prompt(atech=False)))

    def test_R230_sabotage_the_quality_branch_off(self):
        # Sabotage: system_prompt ignores the mode -> the fast text, which
        # lacks every workflow element.
        self.patch(build, "quality_mode", lambda: False)
        miss = missing_elements(self.prompt(atech=False))
        self.assertIn("brief", miss)
        self.assertIn("review rounds", miss)


class TestFastPromptUnchanged(_Mode):
    """Fast mode is the prompt before R230. MEASURED 2026-10-19 (bundled
    freecadcmd, the real kit and library): system_prompt for atech=True,
    'a toy car', 'phone stand with cable hole' and atech=False, taken before
    and after the R230 change with ATECH_PROMPT_MODE=fast, were equal byte
    for byte once the 12 new atech_form.py helper-card lines (R231, meant
    for both modes) were left out."""
    MODE = "fast"

    def test_R230_fast_text_is_the_template_without_the_quality_branch(self):
        a = build.system_prompt(WS, request="a toy car")
        self.patch(build, "quality_mode", lambda: False)
        os.environ["ATECH_PROMPT_MODE"] = "quality"   # the branch alone decides
        b = build.system_prompt(WS, request="a toy car")
        self.assertEqual(a, b)

    def test_R230_fast_text_keeps_its_speed_rules(self):
        flat = _flat(build.system_prompt(WS, request="a toy car"))
        for needle in FAST_ONLY:
            self.assertIn(_flat(needle), flat, needle)
        for name, needle in QUALITY_ELEMENTS:
            if name in ("brief", "review rounds", "fit", "never a box",
                        "check alone", "pass is the floor"):
                self.assertNotIn(_flat(needle), flat, name)

    def test_R230_fast_atech_card_is_the_old_card(self):
        self.atech_library()
        card = build._api_card()
        self.assertTrue(card.startswith(build.ATECH_RULES_HEAD.split("{")[0]))
        for needle in FAST_ONLY_ATECH:
            self.assertIn(_flat(needle), _flat(card), needle)
        self.assertEqual(build.ATECH_RULES,
                         build.ATECH_RULES_HEAD + build.ATECH_FAST_TAIL)

    def test_R230_settings_fast_equals_env_fast(self):
        a = build.system_prompt(WS, atech=False)
        os.environ.pop("ATECH_PROMPT_MODE")
        settings.save(dict(settings.DEFAULTS, agent_quality="fast"))
        self.assertFalse(build.quality_mode())
        self.assertEqual(build.system_prompt(WS, atech=False), a)


class TestModeSettings(_Mode):
    MODE = None

    def test_R230_default_is_quality(self):
        self.assertEqual(settings.DEFAULTS["agent_quality"], "quality")
        self.assertEqual(settings.agent_quality(), "quality")    # no file
        self.assertTrue(build.quality_mode())

    def test_R230_settings_and_env_override(self):
        settings.save(dict(settings.DEFAULTS, agent_quality="fast"))
        self.assertEqual(settings.agent_quality(), "fast")
        self.assertFalse(build.quality_mode())
        os.environ["ATECH_PROMPT_MODE"] = "quality"      # env wins
        self.assertTrue(build.quality_mode())
        os.environ["ATECH_PROMPT_MODE"] = "Fast "
        self.assertFalse(build.quality_mode())
        os.environ["ATECH_PROMPT_MODE"] = "turbo"        # unknown: ignored
        settings.save(dict(settings.DEFAULTS, agent_quality="quality"))
        self.assertTrue(build.quality_mode())

    def test_R230_cfg_values(self):
        q = settings.agent_quality
        self.assertEqual(q({"agent_quality": "fast"}), "fast")
        self.assertEqual(q({"agent_quality": "nonsense"}), "quality")
        self.assertEqual(q({"agent_quality": ""}), "quality")
        self.assertEqual(q({}), "fast")     # a pre-R230 dict keeps fast
        self.assertEqual(q(settings.load()), "quality")

    def test_R230_budget_and_effort_defaults(self):
        s = cli.agent_settings
        Q = dict(settings.DEFAULTS)          # what load() gives: quality
        self.assertEqual(s(Q), {"model": "", "effort": "xhigh",
                                "budget": 25.0})
        self.assertEqual(s(), {"model": "", "effort": "xhigh",
                               "budget": 25.0})            # no settings file
        self.assertEqual(s(dict(Q, agent_budget_usd=7.5))["budget"], 7.5)
        self.assertEqual(s(dict(Q, agent_budget_usd=0))["budget"], 0.0)
        self.assertEqual(s(dict(Q, agent_effort="low"))["effort"], "low")
        self.assertEqual(s(dict(Q, agent_model=" opus "))["model"], "opus")
        # the old saves' 3.00 is the old default, not a choice ...
        self.assertEqual(s(dict(Q, agent_budget_usd=3.0))["budget"], 25.0)
        # ... unless the dialog marked it as the user's own
        self.assertEqual(s(dict(Q, agent_budget_usd=3.0,
                                agent_budget_user=True))["budget"], 3.0)
        self.assertEqual(s(dict(Q, agent_budget_usd="lots"))["budget"], 25.0)
        # fast mode: the defaults before R230
        F = dict(Q, agent_quality="fast")
        self.assertEqual(s(F), {"model": "", "effort": "", "budget": 3.0})
        self.assertEqual(s({}), {"model": None, "effort": None, "budget": 3.0})
        self.assertEqual(s(dict(F, agent_budget_usd=3.0))["budget"], 3.0)

    def test_R230_argv_in_quality_mode(self):
        flags = {"--max-budget-usd", "--effort", "--model", "--allowedTools"}
        a = cli.agent_argv("/w", flags=flags, **cli.agent_settings(
            dict(settings.DEFAULTS)))
        self.assertEqual(a[a.index("--max-budget-usd") + 1], "25.00")
        self.assertEqual(a[a.index("--effort") + 1], "xhigh")
        self.assertNotIn("--model", a)                     # never forced
        a = cli.agent_argv("/w", flags=flags, **cli.agent_settings(
            dict(settings.DEFAULTS, agent_budget_usd=0)))
        self.assertNotIn("--max-budget-usd", a)            # 0 = no limit

    def test_R230_sabotage_budget_default_ignored(self):
        # Sabotage: quality's default budget back at fast's -> caught.
        self.patch(cli, "QUALITY_BUDGET_USD", cli.DEFAULT_BUDGET_USD)
        self.assertNotEqual(cli.agent_settings(dict(settings.DEFAULTS))["budget"],
                            25.0)

    def test_R230_timeouts(self):
        os.environ["ATECH_PROMPT_MODE"] = "fast"
        self.assertEqual(sandbox.default_timeout(), 60.0)
        os.environ["ATECH_PROMPT_MODE"] = "quality"
        self.assertEqual(sandbox.default_timeout(), 180.0)
        ws = tempfile.mkdtemp(prefix="atech-qm-ws-")
        try:
            text = sandbox.wrapper_script(ws, freecadcmd="/fc/bin/freecadcmd",
                                          mode="none")
            self.assertIn("ATECH_CHECK_TIMEOUT=180.0", text)
            self.assertIn(" 210", text)                    # hard stop +30 s
            self.assertIn("flock -w 240 .check.lock", text)
            job = sandbox.Job(ws, freecadcmd="/fc/bin/freecadcmd", mode="none")
            self.assertEqual(job.timeout, 180.0)
            self.assertEqual(sandbox.Job(ws, timeout=7, mode="none").timeout, 7.0)
            os.environ["ATECH_PROMPT_MODE"] = "fast"
            text = sandbox.wrapper_script(ws, freecadcmd="/fc/bin/freecadcmd",
                                          mode="none")
            self.assertIn("ATECH_CHECK_TIMEOUT=60.0", text)
            self.assertIn("flock -w 120 .check.lock", text)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


class TestPanelLimits(_Mode):
    """MAX_FIX_ATTEMPTS / STALL_AFTER_S / BUILD_QUIET_S by mode."""

    WANT = {"MAX_FIX_ATTEMPTS": (2, 5), "STALL_AFTER_S": (60, 300),
            "BUILD_QUIET_S": (300, 900)}

    def test_R230_values_in_the_source(self):
        with open(PANEL_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        cls = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "AgentPanel"][0]
        found, props = {}, set()
        for node in cls.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple):
                names = [t.id for t in node.targets[0].elts]
                vals = [v.value for v in node.value.elts]
                found.update(zip(names, vals))
            if isinstance(node, ast.FunctionDef) and any(
                    getattr(d, "id", None) == "property" for d in node.decorator_list):
                src = ast.unparse(node)
                if "build.quality_mode()" in src:
                    props.add(node.name)
        for name, (fast, quality) in self.WANT.items():
            self.assertEqual(found.get("FAST_" + name), fast, name)
            self.assertEqual(found.get("QUALITY_" + name), quality, name)
            self.assertIn(name, props)

    def test_R230_real_class(self):
        try:
            import PySide6  # noqa: F401
        except ImportError:
            self.skipTest("PySide6 not importable here (runs under freecadcmd)")
        sys.path.insert(0, os.path.dirname(HERE))
        from acadagent import panel, build as rbuild
        dummy = types.SimpleNamespace(**{
            "%s_%s" % (m, n): v[i] for n, v in self.WANT.items()
            for i, m in enumerate(("FAST", "QUALITY"))})
        for mode, i in (("fast", 0), ("quality", 1)):
            os.environ["ATECH_PROMPT_MODE"] = mode
            self.assertEqual(rbuild.quality_mode(), bool(i))
            for name, vals in self.WANT.items():
                self.assertEqual(getattr(panel.AgentPanel, name).fget(dummy),
                                 vals[i], (mode, name))


# ------------------------------------------------------------ R231 / R232
class TestKitFiles(_Mode):
    MODE = "quality"

    def kit(self, files):
        d = tempfile.mkdtemp(prefix="atech-qm-kit-")
        self.addCleanup(shutil.rmtree, d, True)
        for rel, text in files.items():
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
        self.patch(build, "KIT_DIR", d)
        build._HELPERS = None
        return d

    CAD = ('__all__ = ["box", "CadError"] + ["hole"]\n'
           'def box(w, h):\n    """A box w x h. More text."""\n'
           'def hole(at, d=3):\n    """A hole at `at`."""\n'
           'def _private():\n    """no"""\n'
           'class CadError(ValueError):\n    pass\n')
    FORM = ('__all__ = ["loft", "box"]\n'
            'def loft(sections, ruled=False):\n    """A loft through sections."""\n'
            'def box(w, h):\n    """A second box - never listed twice."""\n')
    DETAIL = ('__all__ = ["soften"]\n'
              'def soften(shape, r, min_r=0.3):\n    """Fillet with a ladder."""\n'
              'def not_public():\n    """no"""\n')

    def test_R231_card_lists_all_three_in_order(self):
        self.kit({"atech_cad.py": self.CAD, "atech_form.py": self.FORM,
                  "atech_detail.py": self.DETAIL})
        lines = build.helper_card().splitlines()
        self.assertEqual(lines, [
            "  cad.box(w, h) - A box w x h.",
            "  cad.hole(at, d=3) - A hole at `at`.",
            "  cad.loft(sections, ruled=False) - A loft through sections.",
            "  cad.soften(shape, r, min_r=0.3) - Fillet with a ladder."])

    def test_R231_missing_files_are_skipped(self):
        self.kit({"atech_cad.py": self.CAD, "atech_detail.py": self.DETAIL})
        self.assertEqual([l.split("(")[0] for l in build.helper_card().splitlines()],
                         ["  cad.box", "  cad.hole", "  cad.soften"])
        self.kit({})
        self.assertEqual(build.helper_card(), "")

    def test_R231_R232_prepare_workspace_copies(self):
        d = self.kit({"atech_cad.py": self.CAD, "atech_form.py": self.FORM,
                      "examples/TRAPS.md": "traps\n", "examples/a.py": "x = 1\n",
                      "reference/ATECH_PRODUCTS.md": "# catalogue\n",
                      "reference/notes.txt": "not md\n"})
        ws = tempfile.mkdtemp(prefix="atech-qm-ws-")
        self.addCleanup(shutil.rmtree, ws, True)
        victim = tempfile.mkdtemp(prefix="atech-qm-victim-")
        self.addCleanup(shutil.rmtree, victim, True)
        os.symlink(victim, os.path.join(ws, "reference"))  # a planted link
        self.patch(sandbox, "wrapper_script", lambda *a, **k: None)
        self.patch(build, "start_turn", lambda *a, **k: None)
        written = build.prepare_workspace(ws)
        self.assertIn("atech_form.py", written)
        self.assertNotIn("atech_detail.py", written)           # not in the kit
        self.assertIn("reference/ATECH_PRODUCTS.md", written)
        ref = os.path.join(ws, "reference")
        self.assertFalse(os.path.islink(ref))
        self.assertEqual(os.listdir(victim), [])                # never followed
        self.assertEqual(sorted(os.listdir(ref)), ["ATECH_PRODUCTS.md"])
        with open(os.path.join(ref, "ATECH_PRODUCTS.md")) as fh:
            self.assertEqual(fh.read(), "# catalogue\n")
        self.assertEqual(os.stat(os.path.join(ref, "ATECH_PRODUCTS.md")).st_mode
                         & 0o777, 0o444)
        self.assertTrue(build.kit_reference("ATECH_PRODUCTS.md"))
        self.assertFalse(build.kit_reference("NOPE.md"))
        # idempotent: nothing rewritten on the next turn
        self.assertEqual([w for w in build.prepare_workspace(ws)
                          if w.startswith("reference/")], [])
        self.assertTrue(os.path.isdir(d))

    def test_R231_sabotage_card_without_the_new_files(self):
        self.kit({"atech_cad.py": self.CAD, "atech_form.py": self.FORM,
                  "atech_detail.py": self.DETAIL})
        # Sabotage: the card reads atech_cad.py alone (before R231).
        self.patch(build, "KIT_MODULES", ("atech_cad.py",))
        self.assertNotIn("cad.loft(", build.helper_card())


# ------------------------------------------------------------------ R233
class _VO(object):
    """A ViewObject stub that records the order of its property sets."""

    def __init__(self, default):
        object.__setattr__(self, "log", [])
        object.__setattr__(self, "ShapeColor", tuple(default) + (0.0,))
        object.__setattr__(self, "Transparency", 0)

    def __setattr__(self, k, v):
        self.log.append(k)
        object.__setattr__(self, k, v)


class TestColourTransparency(_Mode):

    def run_colour(self, view, names=("A", "B", "C")):
        default = (0.8, 0.8, 0.8)
        self.patch(build, "_default_shape_color", lambda: default)
        bodies = [types.SimpleNamespace(Name=n, Label=n, ViewObject=_VO(default))
                  for n in names]
        fc = types.ModuleType("FreeCAD")
        fc.GuiUp = 1
        saved = sys.modules.get("FreeCAD")
        sys.modules["FreeCAD"] = fc
        try:
            build._colour(bodies, view)
        finally:
            if saved is None:
                sys.modules.pop("FreeCAD", None)
            else:
                sys.modules["FreeCAD"] = saved
        return {b.Name: b.ViewObject for b in bodies}

    def test_R233_transparency_applied_last(self):
        vo = self.run_colour({"A": {"Transparency": 60.4,
                                    "ShapeColor": [0.1, 0.2, 0.3],
                                    "DiffuseColor": [[0.1, 0.2, 0.3, 0.0]]}})
        a = vo["A"]
        self.assertEqual(a.Transparency, 60)
        self.assertEqual(a.ShapeColor, (0.1, 0.2, 0.3))
        self.assertEqual(a.DiffuseColor, [[0.1, 0.2, 0.3, 0.0]])
        self.assertEqual(a.log[-1], "Transparency")

    def test_R233_palette_colour_keeps_it(self):
        vo = self.run_colour({"B": {"Transparency": 70}})
        b = vo["B"]
        self.assertIn(b.ShapeColor, build.PALETTE)      # got a palette colour
        self.assertEqual(b.Transparency, 70)
        self.assertEqual(b.log[-1], "Transparency")     # set again after it
        self.assertEqual(vo["A"].Transparency, 0)

    def test_R233_sabotage_order_is_detected(self):
        # Sabotage: Transparency first, then the colours (the dict order a
        # script that sets Transparency before ShapeColor records).
        vo = self.run_colour({"A": {"Transparency": 50,
                                    "ShapeColor": [0.1, 0.2, 0.3]}})
        log = [k for k in vo["A"].log if k in ("Transparency", "ShapeColor")]
        self.assertEqual(log, ["ShapeColor", "Transparency"])
        self.assertNotEqual(log, ["Transparency", "ShapeColor"])


if __name__ == "__main__":
    unittest.main()
