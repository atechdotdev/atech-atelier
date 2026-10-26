"""R270-R275: the quality prompt's round-1 rewrite (WS1 of the launch eval).

    R270  START FROM THE CLOSEST PRODUCT EXAMPLE (R600: its hardware and fit
          code kept, its silhouette REDESIGNED freely - not restyled within
          its knobs); the rule names every product example on disk
          (build.product_examples scans the docstrings). "never copy its
          box" is atech_case.py's rule alone.
    R271  SHIP IN STAGES: Stage A (a CHECK PASS product with every module's
          working-face opening and the fasteners), the detail list, then the
          review rounds, each ending on a passing ./check. R510: no minutes
          (no stage times, no stop minute, no TURN CLOCK rule) - the result
          counts, not how long it takes.
    R272  the brief cap (about 25 lines besides the detail list)
          and the detail list ordered by visibility, 15 items outside.
    R273  the category words (R600: design inspiration, never minimums or
          gates); the hardware sets a minimum pocket, never the outline;
          modules cabled where the design needs them.
    R274  ROBUST FORMS (lines + tangent arcs, revolve/loft; after two
          failures the documented fallback, cad.shell_body when the kit has
          it, or the example's construction) and QUALITY_STUCK 8 -> 3.
    R275  settings: the mode-default effort exposed (quality_default_effort,
          mode_default_effort, effective_effort, $ATECH_AGENT_EFFORT).

System Python, no FreeCAD (the stubbed package of test_claude_cli).

RUN
    cd addon/AcadAgent/tests && python3 -m unittest test_quality_prompt_r270 -v
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_quality_mode import (_Mode, _flat, missing_elements,  # noqa: E402
                               build, cli, settings)

WS = "/nonexistent/ws"
EXAMPLES = os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit",
                        "examples")


def disk_product_examples(folder=EXAMPLES):
    """The product examples, found independently of build.product_examples:
    a module docstring opening with 'Example: "<request>"'."""
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py") or name == "atech_case.py":
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            if re.match(r'\s*(?:"""|\'\'\')\s*Example:\s*"', fh.read()):
                out.append(name)
    return out


# (name, needle) on the whitespace-flattened prompt. R600 (the user,
# 2026-10-26: "it overfits too much to be a box now"): the example is
# working hardware and fit code to keep, its silhouette redesigned freely;
# the archetypes are design words, never minimums or gates.
R270_ELEMENTS = [
    # R270/R600 the example
    ("start from", "START FROM THE CLOSEST PRODUCT EXAMPLE"),
    ("start: fit code", "It is working hardware and fit code"),
    ("start: keep", "KEEP that code"),
    ("start: redesign", "REDESIGN the silhouette freely for this request"),
    # R271/R510 results, not time
    ("results not time", "the result is what counts, not how long it takes"),
    ("last pass", "keep the last passing build"),
    # R272 the brief cap
    ("brief cap", "about 25 lines plus the detail list"),
    ("exterior 15", "at least 15 on the outside"),
    # R273/R600 the design words
    ("design words", "Design words by category (inspiration, never rules)"),
    ("vehicle words", "vehicle: long and low, a wheel at each corner under "
                      "its arch"),
    ("speaker words", "a form you want on a shelf, never a slab"),
    ("robot words", "a big head with a face - the screen as eyes"),
    ("look: box", "If it reads as a box or a slab, redesign the outlines now"),
    # R274
    ("robust", "ROBUST FORMS: straight lines and tangent arcs"),
    ("robust fallback", "fails twice on one body, switch to"),
    ("no hand-rolled", "never a hand-rolled boolean shell"),
    ("stuck 3", "fails ./check 3 times in a row"),
]
# Atech turns also carry these (the hardware half of DESIGN THE PRODUCT, the
# card).
R270_ATECH = [
    ("hardware pocket", "the hardware sets a minimum inner pocket, nothing "
                        "more"),
    ("orientation suits", "Choose the board orientation to suit the form"),
    ("cable for the design", "Where a port happens to sit never decides "
                             "where a feature goes"),
    ("card: atech_case", "examples/atech_case.py shows the library calls; "
                         "never copy its box"),
]
# Wording R273 / R600 removed: the board footprint as the silhouette, and the
# archetype minimums and restyle-within-knobs that pulled toward boxes and
# checker-gaming.
GONE = ["never picked first", "the overall size, derived from the measured "
        "hardware", "Size every body from cad.bound_of",
        "ARCHETYPE FIRST", "1.8-2.5 x the width", "40 % of the front face",
        "with its minimum size", "A plain product that meets all of that is "
        "shippable", "RESTYLE it", "restyle here", "FORK THE CLOSEST",
        "ARCHETYPE GATE"]


def missing_r270(prompt, atech=False, examples=None):
    """Names of the R270 elements a prompt lacks; 'example <file>' for each
    product example on disk the fork rule does not name; 'gone: <text>'
    for removed wording that is back (Atech turns)."""
    flat = _flat(prompt)
    miss = [n for n, needle in R270_ELEMENTS + (R270_ATECH if atech else [])
            if _flat(needle) not in flat]
    fork = flat[flat.find("START FROM THE CLOSEST PRODUCT EXAMPLE"):]
    for name in (disk_product_examples() if examples is None else examples):
        if name not in fork[:2000]:
            miss.append("example " + name)
    miss += ["gone: " + g for g in GONE if _flat(g) in flat]
    return miss


def never_copy_violations(prompt):
    """Each 'never copy' that is NOT about atech_case.py: the sentence it is
    in must name atech_case.py (R270 - the product examples are forked)."""
    flat = _flat(prompt)
    bad = []
    for m in re.finditer(r"never copy", flat):
        start = max(flat.rfind(". ", 0, m.start()), flat.rfind("\n", 0,
                                                              m.start()))
        sentence = flat[start:m.end()]
        if "atech_case.py" not in sentence:
            bad.append(flat[max(0, m.start() - 120):m.end() + 40])
    return bad


class _R270(_Mode):
    MODE = "quality"

    def prompt(self, **kw):
        return build.system_prompt(WS, **kw)


class TestR270Prompt(_R270):

    def test_R270_examples_scanned_from_disk(self):
        rows = build.product_examples()
        self.assertEqual([f for f, _r, _a in rows], disk_product_examples())
        self.assertGreaterEqual(len(rows), 3)
        arch = {f: a for f, _r, a in rows}
        self.assertEqual(arch.get("toy_car.py"), "vehicle")
        self.assertEqual(arch.get("desk_robot.py"), "robot or character")
        self.assertEqual(arch.get("smart_speaker.py"), "speaker")
        self.assertNotIn("atech_case.py", arch)

    def test_R270_every_element_non_atech(self):
        for kw in ({"atech": False}, {"request": "a toy car"},
                   {"request": "a retro handheld game"}):
            sp = self.prompt(**kw)
            self.assertEqual(missing_r270(sp), [], kw)
            self.assertEqual(missing_elements(sp), [], kw)   # R230 still whole

    def test_R270_every_element_atech(self):
        self.atech_library()
        self.patch(build, "kit_reference", lambda name: True)
        sp = self.prompt(atech=True)
        self.assertEqual(missing_r270(sp, atech=True), [])
        self.assertEqual(missing_elements(sp, atech=True), [])

    def test_R270_never_copy_only_for_atech_case(self):
        self.atech_library()
        sp = self.prompt(atech=True)
        flat = _flat(sp)
        self.assertIn("examples/atech_case.py shows the library calls; never "
                      "copy its box", flat)
        self.assertEqual(never_copy_violations(sp), [])
        # ... and the start rule tells the agent atech_case.py is no product.
        self.assertIn("examples/atech_case.py is not a product: never copy "
                      "its box", flat)
        # The card's never-copy sentence is atech_case.py's.
        card = _flat(build._api_card())
        at = card.index("never copy its box")
        self.assertIn("examples/atech_case.py shows the library calls",
                      card[max(0, at - 300):at])

    def test_R270_fork_ahead_of_the_box_rule_order(self):
        # The fork rule sits in step 3 (the first write), after the reads.
        flat = _flat(self.prompt(atech=False))
        start = flat.index("START FROM THE CLOSEST PRODUCT EXAMPLE")
        self.assertLess(flat.index("READ only what you need"), start)
        self.assertLess(flat.index("WRITE intent.json, then model.py"), start)
        self.assertLess(start, flat.index("REVIEW at least"))
        # R600: the design comes before the process
        self.assertLess(flat.index("DESIGN THE PRODUCT, NOT A CASE"),
                        flat.index("THE WORKFLOW"))
        self.assertIn("the example you start from", flat)

    def test_R270_a_new_example_is_listed_when_it_lands(self):
        tmp = tempfile.mkdtemp(prefix="atech-r270-kit-")
        try:
            ex = os.path.join(tmp, "examples")
            os.makedirs(ex)
            for name in ("toy_car.py", "atech_case.py", "bracket.py"):
                shutil.copy(os.path.join(EXAMPLES, name), ex)
            with open(os.path.join(ex, "game_boy.py"), "w") as fh:
                fh.write('"""Example: "a retro handheld" - two grips.\n"""\n'
                         'x = 1\n')
            with open(os.path.join(ex, "night_owl.py"), "w") as fh:
                fh.write('"""Example: "an owl night light".\n\nARCHETYPE: '
                         'lamp.\n"""\n')
            self.patch(build, "KIT_DIR", tmp)
            rows = build.product_examples()
            self.assertEqual(rows, [
                ("game_boy.py", "a retro handheld", "handheld"),
                ("night_owl.py", "an owl night light", "lamp"),
                ("toy_car.py", "a toy car", "vehicle")])
            sp = self.prompt(atech=False)
            self.assertEqual(missing_r270(sp, examples=[
                "game_boy.py", "night_owl.py", "toy_car.py"]), [])
            self.assertNotIn("bracket.py \"", sp)
            # No product example at all: no fork rule (nothing to name).
            for f in os.listdir(ex):
                if f != "atech_case.py":
                    os.remove(os.path.join(ex, f))
            self.assertEqual(build.product_examples(), [])
            self.assertEqual(build.fork_rule(), "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_R510_no_minutes_in_the_quality_prompt(self):
        """R510 ("results, not how long it takes"): no stage minutes, no
        stop minute, no brief time, no TURN CLOCK rule - whether or not
        the kit's ./check prints the clock."""
        for clock in (True, False):
            self.patch(build, "kit_prints_clock", lambda c=clock: c)
            for off in ("", "levels"):
                os.environ["ATECH_PROMPT_OFF"] = off
                sp = self.prompt(atech=False, request="a toy car")
                flat = _flat(sp)
                for gone in ("TURN CLOCK", "add nothing new",
                             "do not deliberate", "minutes in silence",
                             "by about", "Count the minutes"):
                    self.assertNotIn(gone, flat, (clock, off, gone))
                self.assertIsNone(re.search(r"\b\d+ min\b(?!\)\.)", re.sub(
                    r"slows to 3 min", "", flat)), (clock, off))
        os.environ.pop("ATECH_PROMPT_OFF", None)
        self.assertFalse(hasattr(build, "QUALITY_STAGES"))
        self.assertFalse(hasattr(build, "QUALITY_BRIEF_MIN"))
        # the good process stays: end on a passing ./check, keep the last
        flat = _flat(self.prompt(atech=False))
        self.assertIn("End on a passing ./check; keep the last passing build",
                      flat)

    def test_R274_fallback_names_shell_body_only_when_the_kit_has_it(self):
        real = build._kit_helper
        self.patch(build, "_kit_helper",
                   lambda n: True if n == "shell_body" else real(n))
        flat = _flat(self.prompt(atech=False))
        self.assertIn("switch to cad.shell_body or the example's construction",
                      flat)
        self.patch(build, "_kit_helper",
                   lambda n: False if n == "shell_body" else real(n))
        flat = _flat(self.prompt(atech=False))
        # R270: the helper card lists the REAL kit's cad.shell_body (WS2
        # added it), so only the fallback sentence must not name it
        self.assertNotIn("switch to cad.shell_body", flat)
        self.assertIn("switch to the example's construction for that body",
                      flat)

    def test_R274_stuck_is_3(self):
        self.assertEqual(build.QUALITY_STUCK, 3)

    def test_R270_fast_mode_untouched(self):
        os.environ["ATECH_PROMPT_MODE"] = "fast"
        flat = _flat(build.system_prompt(WS, request="a toy car"))
        for needle in ("START FROM THE CLOSEST PRODUCT EXAMPLE",
                       "DESIGN THE PRODUCT, NOT A CASE",
                       "Design words by category", "ROBUST FORMS"):
            self.assertNotIn(needle, flat)


class TestR270Sabotage(_R270):
    """Every R270 gate fails when its rule is taken out."""

    def test_sabotage_fork_rule_deleted(self):
        self.patch(build, "fork_rule", lambda: "")
        miss = missing_r270(self.prompt(atech=False))
        self.assertIn("start from", miss)
        self.assertIn("example toy_car.py", miss)

    def test_sabotage_fork_rule_misses_an_example(self):
        rows = build.product_examples()
        self.patch(build, "product_examples", lambda: rows[1:])
        miss = missing_r270(self.prompt(atech=False))
        self.assertIn("example " + rows[0][0], miss)

    def test_sabotage_box_look_deleted(self):
        self.patch(build, "QUALITY_WORKFLOW", build.QUALITY_WORKFLOW.replace(
            "If it reads\n   as a box or a slab, redesign the outlines now", ""))
        self.assertIn("look: box", missing_r270(self.prompt(atech=False)))

    def test_sabotage_results_sentence_deleted(self):
        self.patch(build, "QUALITY_PACE", "")
        self.assertIn("results not time",
                      missing_r270(self.prompt(atech=False)))

    def test_sabotage_design_words_deleted(self):
        t = build.QUALITY_PROMPT
        a = t.index("Design words by category")
        b = t.index("{fit_head}")
        self.patch(build, "QUALITY_PROMPT", t[:a] + t[b:])
        miss = missing_r270(self.prompt(atech=False))
        self.assertIn("design words", miss)
        self.assertIn("vehicle words", miss)

    def test_sabotage_archetype_minimum_back(self):
        rows = [(lab, w, rule + " (length 1.8-2.5 x the width)")
                for lab, w, rule in build.ARCHETYPES]
        self.patch(build, "ARCHETYPES", tuple(rows))
        miss = missing_r270(self.prompt(atech=False))
        self.assertIn("gone: 1.8-2.5 x the width", miss)

    def test_sabotage_stuck_back_to_8(self):
        self.patch(build, "QUALITY_STUCK", 8)
        self.assertIn("stuck 3", missing_r270(self.prompt(atech=False)))

    def test_sabotage_never_copy_on_the_product_examples(self):
        self.atech_library()
        self.patch(build, "ATECH_QUALITY_TAIL", build.ATECH_QUALITY_TAIL.replace(
            "{products}",
            "\nThe product examples: never copy their shape either.{products}"))
        build._CARD = None
        self.assertNotEqual(never_copy_violations(self.prompt(atech=True)), [])

    def test_sabotage_hardware_first_sizing_back(self):
        self.atech_library()
        self.patch(build, "HW_DESIGN", build.HW_DESIGN + (
            "- Size every body from cad.bound_of(board, *modules, *ribbons) "
            "plus\n  clearance and wall; never picked first.\n"))
        miss = missing_r270(self.prompt(atech=True), atech=True)
        self.assertIn("gone: never picked first", miss)


class TestR275Effort(_Mode):
    MODE = None

    def setUp(self):
        super().setUp()
        self._eff = os.environ.pop(settings.EFFORT_ENV, None)

    def tearDown(self):
        os.environ.pop(settings.EFFORT_ENV, None)
        if self._eff is not None:
            os.environ[settings.EFFORT_ENV] = self._eff
        super().tearDown()

    def test_R275_in_step_with_the_cli(self):
        self.assertEqual(settings.QUALITY_EFFORT, cli.QUALITY_EFFORT)
        self.assertEqual(settings.QUALITY_EFFORT, "xhigh")   # still default
        self.assertEqual(tuple(settings.EFFORT_LEVELS), tuple(cli.EFFORTS))
        # The CLI's default turn runs at the effort settings reports.
        self.assertEqual(cli.agent_settings(dict(settings.DEFAULTS))["effort"],
                         settings.effective_effort(dict(settings.DEFAULTS)))

    def test_R275_mode_default_and_effective(self):
        Q = dict(settings.DEFAULTS)
        F = dict(Q, agent_quality="fast")
        self.assertEqual(settings.mode_default_effort(Q), "xhigh")
        self.assertEqual(settings.mode_default_effort(F), "")
        self.assertEqual(settings.effective_effort(Q), "xhigh")
        self.assertEqual(settings.effective_effort(dict(Q, agent_effort=" High ")),
                         "high")                       # the user's own wins
        self.assertEqual(settings.effective_effort(F), "")
        self.assertEqual(settings.effective_effort(), "xhigh")   # no file

    def test_R275_env_moves_only_the_default(self):
        os.environ[settings.EFFORT_ENV] = "high"
        Q = dict(settings.DEFAULTS)
        self.assertEqual(settings.quality_default_effort(), "high")
        self.assertEqual(settings.effective_effort(Q), "high")
        self.assertEqual(settings.effective_effort(dict(Q, agent_effort="low")),
                         "low")
        self.assertEqual(settings.mode_default_effort(
            dict(Q, agent_quality="fast")), "")
        os.environ[settings.EFFORT_ENV] = "ludicrous"     # unknown: ignored
        self.assertEqual(settings.effective_effort(Q), "xhigh")

    def test_R275_sabotage_default_drift_is_caught(self):
        self.patch(settings, "QUALITY_EFFORT", "high")
        self.assertNotEqual(settings.QUALITY_EFFORT, cli.QUALITY_EFFORT)


if __name__ == "__main__":
    unittest.main()
