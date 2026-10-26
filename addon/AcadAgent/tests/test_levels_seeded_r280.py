"""R430-R433 (WS3): seed-aware design levels.

    R430  atech_levels.level_text / level_message take `seed`: a seeded
          LEVEL 1 keeps the example's hardware and fit code and (R600)
          REDESIGNS its silhouette freely for the request (ends on CHECK
          PASS, never as a box or a slab);
          seeded LEVELS 2-5 verify against their GATE and change only what
          fails it. advance() carries the seed from the marker; build's
          quality_prompt passes it (from the ladder on a level turn too).
          The unseeded texts are byte for byte what they were (LEVEL 1:
          as R600 reworded it, design-first).
    R431  every seeded checklist starts with the hero rule (R600: never
          seal a working opening; move it with its module).
    R432  LEVELS 1 and 6 carry the archetype's design words
          (build.archetype_note). R600 (the user, 2026-10-26: "it overfits
          too much to be a box now"): an advisory checklist note, never a
          GATE, and no minimum numbers anywhere.
    R433  the seeded ladder's minutes (atech_levels.SEEDED_*), in the
          prompt and in each seeded level's TIME line.

Every gate here has a sabotage test: the contradicting text put back must
fail it. System Python only.

RUN
    cd addon/AcadAgent/tests && python3 -m unittest test_levels_seeded_r280 -v
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_quality_mode import _Mode, build  # noqa: E402

KIT = os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit")
sys.path.insert(0, KIT)
import atech_levels as lv  # noqa: E402

WS = "/nonexistent/ws"

#: sha256 of the unseeded level_text(n) (default numbers) before R430.
UNSEEDED_SHA = {
    # R600: LEVEL 1 reworded design-first (the product's own masses, never
    # the board's box; the user's numbers)
    1: "3d9c55747302f68e7214b484d30bb37f30a081391d19a805544dccd161284dd6",
    2: "b41cb71d227b5a702dfa1933238ea1f926e60442a5aef28844a63a6a9b9809f3",
    3: "565636302e049dc1981742679217b108377f9e5fdc3fe52a07c58ef632ec2d1e",
    4: "f2996f7bc10ccba1e10c7219d62676ddd96d15b87b97c590b474073749dccaad",
    5: "6e44334418a360ef4ad509c1d5132ebbf724289499f7fe6ee85e896bc9a3e8cb",
    6: "841640d6eff07fb5e205af243d9a03e4e41314fbd1416bbbf8e4233c635d67ff",
    7: "fd02658a080f39e4e7110bc046f71285fe8ae3f012233c9387d07efbb3e01e9d",
    8: "73dfe809b4c31fde1dbc45200849307ff11361fadf51c90329654f84919f7f69",
    9: "6832716d7fa4179c5d73527306509246e66b3c7a60889d6d2aa30b2169cc1467",
}
#: sha256 of level_message(n, details=25, exterior=15, flaws=5,
#: brief_lines=20) before R430 (the keywords run_eval / build pass).
UNSEEDED_MSG_SHA = {
    1: "7154bc2afa49a323985fdef4948fe5e8b464e5b7cdab3454cc222277f1ca045e",
    2: "801f7690ff6cef0635d9a5cc9bd61a70382a4422be351acb10f7e4a3b5b6ea9e",
    3: "07b355d6496ef010eac3a85b9f8e51e23536a1f078252bffa58fd9e301369f1e",
    4: "14af27e4206fd6c550b4e4485d56aa443e552e1136003bb749854bc8aaa803a3",
    5: "3dc6ab5a78ab3ab922dff41fe9acd1ec52cea42441adb9dae2845241d8cb95a8",
    6: "ebe8860805518dd7cbc5c54bc0745241a9a88baaa3e85f2215038217af02bf80",
    7: "bd04eda19b415fbda1da70abe5671daa063a23b3540bb60cc35ba4ce9b82e7af",
    8: "42e0118494bcdb84b0de9b61f2e75ad410ea29978c392239cdb49f5a57e83407",
    9: "3de5cfb992ab5f37d3fde54e713dc7965fa6e075e56aa37d7de1c3dc25d51798",
}

#: Text that tells a seeded agent to throw the passing product away (the
#: unseeded ladder's build-it-new wording). None may reach a seeded turn.
CONTRADICTIONS = (
    "no hollowing", "no openings yet", "volume model - the main masses",
    "main masses as solids", "hollow every housing to one uniform wall",
    "before any opening is cut (cad.profile_body", "no example was seeded",
    "split it into parts along a designed break line",
)
HERO = "- never seal a working opening or drop a lens the hardware needs"
#: R600: the restyle-within-knobs wording a seeded LEVEL 1 must not carry.
RESTYLE_GONE = ("restyle it", "restyle knobs", "the aspect ratio, the stance "
                "and the hero size", "with its minimum size")
VERIFY = "verify against the gate; change only what fails it"


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _flat(text):
    """Lower case, whitespace folded (the texts wrap at fixed columns)."""
    return " ".join(text.lower().split())


def _contradictions(text):
    low = _flat(text)
    return [c for c in CONTRADICTIONS if c in low]


def _ws(test):
    d = tempfile.mkdtemp(prefix="r430-")
    test.addCleanup(shutil.rmtree, d, True)
    return d


def _checklist(text):
    """The level block's checklist: the lines between the title and GATE."""
    return text.split("\n", 1)[1].split("\nGATE: ", 1)[0]


class SeededWording(unittest.TestCase):
    """R430 / R431: the seeded texts."""

    def test_seeded_level_one_restyles_never_strips(self):
        t = lv.level_text(1, seed="toy_car.py")
        self.assertEqual(_contradictions(t), [])
        low = _flat(t)
        for want in ("keep its hardware and fit code",
                     "its body is not your design: redesign the silhouette "
                     "freely for this request",
                     "move the hardware where the new form needs it",
                     "never as a box or a slab",
                     "end on check pass", "examples/toy_car.py"):
            with self.subTest(want=want):
                self.assertIn(want, low)
        for gone in RESTYLE_GONE:
            with self.subTest(gone=gone):
                self.assertNotIn(gone, low)
        self.assertNotIn("No hollowing", t)
        self.assertNotIn("no openings yet", t)
        # the brief and its numbers stay
        t = lv.level_text(1, details=31, exterior=17, brief_lines=20,
                          seed="toy_car.py")
        self.assertIn("at least 31 items, at least 17 on the outside", t)
        self.assertIn("at most 20 lines", t)

    def test_seeded_levels_two_to_five_verify_against_the_gate(self):
        for n in range(2, 6):
            t = lv.level_text(n, seed="smart_speaker.py")
            with self.subTest(level=n):
                self.assertIn(VERIFY, _flat(_checklist(t)))
                self.assertEqual(_contradictions(t), [])
                self.assertNotEqual(_sha(t), UNSEEDED_SHA[n])

    def test_every_seeded_checklist_starts_with_the_hero_rule(self):
        for n in range(1, lv.COUNT + 1):
            t = lv.level_text(n, seed="desk_robot.py")
            with self.subTest(level=n):
                self.assertTrue(_checklist(t).lower().startswith(HERO), t[:200])
                self.assertIn("examples/desk_robot.py", _checklist(t))
                self.assertTrue(t.startswith("LEVEL %d of 9 - " % n))
                self.assertIn("\nGATE: ", t)
                self.assertNotRegex(t, r"\{[a-z_]+\}")
                # the later levels keep their own work
                if n >= 6:
                    self.assertIn(lv.LEVELS[n - 1][2].format(
                        details=25, exterior=15, flaws=5, brief_lines=25), t)

    def test_unseeded_levels_are_byte_identical(self):
        for n in range(1, lv.COUNT + 1):
            with self.subTest(level=n):
                self.assertEqual(_sha(lv.level_text(n)), UNSEEDED_SHA[n])
                self.assertEqual(_sha(lv.level_text(n, seed=None)),
                                 UNSEEDED_SHA[n])
                self.assertEqual(_sha(lv.level_message(
                    n, details=25, exterior=15, flaws=5, brief_lines=20)),
                    UNSEEDED_MSG_SHA[n])
        self.assertIn("No hollowing and no openings yet.", lv.level_text(1))
        # R600: design-first wording, no archetype minimums
        low = _flat(lv.level_text(1))
        self.assertIn("never from the board's box", low)
        self.assertIn("never as a box or a slab", low)
        self.assertNotIn("minimum size", low)

    def test_seeded_message_is_still_a_level_turn(self):
        msg = lv.level_message(3, seed="toy_car.py")
        self.assertTrue(lv.is_level_turn(msg))
        self.assertFalse(build.is_fix_turn(msg))


class Sabotage(unittest.TestCase):
    """Putting the build-it-new wording back must fail the gates above."""

    def _run(self, *names):
        suite = unittest.TestSuite(SeededWording(n) for n in names)
        res = unittest.TestResult()
        suite.run(res)
        return res

    def _patch_seeded(self, n, text):
        saved = dict(lv.SEEDED)
        self.addCleanup(lambda: (lv.SEEDED.clear(), lv.SEEDED.update(saved)))
        lv.SEEDED[n] = text

    def test_no_hollowing_back_in_seeded_level_one_fails(self):
        check, gate = lv.SEEDED[1]
        self._patch_seeded(1, (check + "\n  No hollowing and no openings "
                               "yet.", gate))
        self.assertIn("no hollowing", _contradictions(
            lv.level_text(1, seed="toy_car.py")))
        res = self._run("test_seeded_level_one_restyles_never_strips")
        self.assertFalse(res.wasSuccessful())

    def test_unseeded_level_one_for_a_seed_fails(self):
        _t, _p, check, gate = lv.LEVELS[0]
        self._patch_seeded(1, (check, gate))
        res = self._run("test_seeded_level_one_restyles_never_strips")
        self.assertFalse(res.wasSuccessful())

    def test_unseeded_shell_level_for_a_seed_fails(self):
        _t, _p, check, gate = lv.LEVELS[3]
        self._patch_seeded(4, (check, gate))
        res = self._run("test_seeded_levels_two_to_five_verify_against_the_gate")
        self.assertFalse(res.wasSuccessful())

    def test_hero_rule_dropped_fails(self):
        saved = lv.HERO_RULE
        self.addCleanup(setattr, lv, "HERO_RULE", saved)
        lv.HERO_RULE = "- Keep the seed's openings where they are."
        res = self._run("test_every_seeded_checklist_starts_with_the_hero_rule")
        self.assertFalse(res.wasSuccessful())

    def test_restyle_wording_back_in_seeded_level_one_fails(self):
        check, gate = lv.SEEDED[1]
        self._patch_seeded(1, (check + "\n- RESTYLE it within its knobs.",
                               gate))
        res = self._run("test_seeded_level_one_restyles_never_strips")
        self.assertFalse(res.wasSuccessful())

    def test_unseeded_text_changed_fails(self):
        saved = lv.LEVELS
        self.addCleanup(setattr, lv, "LEVELS", saved)
        first = list(saved[0])
        first[2] = first[2].replace("No hollowing", "Hollow it")
        lv.LEVELS = (tuple(first),) + saved[1:]
        res = self._run("test_unseeded_levels_are_byte_identical")
        self.assertFalse(res.wasSuccessful())


class Marker(unittest.TestCase):
    """R430 / R432: advance() carries the seed and the archetype line."""

    def test_advance_carries_the_seed_through_every_level(self):
        ws = _ws(self)
        gate = build.archetype_note("vehicle")
        lv.write(ws, 1, "toy_car.py", gate)
        self.assertEqual(lv.read(ws), {"level": 1, "count": 9,
                                       "seed": "toy_car.py",
                                       "archetype": gate})
        for n in range(2, lv.COUNT + 1):
            msg = lv.advance(ws)
            with self.subTest(level=n):
                self.assertTrue(msg.startswith("LEVEL %d of 9" % n))
                self.assertEqual(lv.read(ws)["seed"], "toy_car.py")
                self.assertEqual(lv.read(ws)["archetype"], gate)
                self.assertTrue(_checklist(msg).lower().startswith(HERO))
                self.assertEqual(_contradictions(msg), [])
                self.assertEqual(gate in msg, n in lv.ARCHETYPE_LEVELS)
                # R600: a checklist note, never part of the GATE
                self.assertNotIn(gate, msg.split("\nGATE: ", 1)[1])
                self.assertTrue(lv.is_level_turn(msg))
        self.assertIsNone(lv.advance(ws))

    def test_unseeded_marker_and_messages_are_unchanged(self):
        ws = _ws(self)
        lv.write(ws, 1)
        with open(os.path.join(ws, lv.MARKER)) as fh:
            self.assertEqual(json.load(fh), {"level": 1, "count": 9, "seed": None})
        for n in range(2, lv.COUNT + 1):
            msg = lv.advance(ws, details=25, exterior=15, flaws=5, brief_lines=20)
            with self.subTest(level=n):
                self.assertEqual(_sha(msg), UNSEEDED_MSG_SHA[n])

    def test_build_next_level_is_seeded(self):
        ws = _ws(self)
        lv.write(ws, 1, "bedside_lamp.py")
        msg = build.next_level(ws)
        self.assertIn(VERIFY, _flat(msg))
        self.assertIn("examples/bedside_lamp.py", msg)

    def test_caller_keyword_wins(self):
        ws = _ws(self)
        lv.write(ws, 1, "toy_car.py")
        msg = lv.advance(ws, seed=None, details=25, exterior=15, flaws=5,
                         brief_lines=20)
        self.assertEqual(_sha(msg), UNSEEDED_MSG_SHA[2])


class Budget(unittest.TestCase):
    """R433: the seeded ladder's minutes."""

    def test_constants(self):
        self.assertEqual(lv.SEEDED_LEVEL1_MIN, 10)
        self.assertEqual(lv.SEEDED_LEVEL_MIN, 8)
        self.assertEqual(lv.SEEDED_LEVEL_STOP, 15)
        self.assertEqual(lv.budget(1, "toy_car.py"), (10, 15))
        self.assertEqual(lv.budget(5, "toy_car.py"), (8, 15))
        self.assertEqual(lv.budget(1), (lv.LEVEL1_MIN, lv.LEVEL_STOP))
        self.assertEqual(lv.budget(5), (lv.LEVEL_MIN, lv.LEVEL_STOP))

    def test_seeded_levels_carry_their_time(self):
        self.assertIn("TIME: about 10 min for this level; past 15 min",
                      lv.level_text(1, seed="toy_car.py"))
        self.assertIn("TIME: about 8 min for this level; past 15 min",
                      lv.level_text(7, seed="toy_car.py"))
        self.assertNotIn("TIME:", lv.level_text(7))

    def test_budget_sabotage(self):
        saved = lv.SEEDED_LEVEL1_MIN
        self.addCleanup(setattr, lv, "SEEDED_LEVEL1_MIN", saved)
        lv.SEEDED_LEVEL1_MIN = 30
        res = unittest.TestResult()
        Budget("test_constants").run(res)
        self.assertFalse(res.wasSuccessful())


class Archetypes(unittest.TestCase):
    """R432/R600: the archetype words are advisory design notes - no
    minimums, no gates."""

    @staticmethod
    def _numbers(rules):
        """(label, text) of every archetype rule that states a number."""
        import re
        return [(lab, rule) for lab, _w, rule in rules
                if re.search(r"\d", rule)]

    def test_no_minimums_in_the_words(self):
        self.assertEqual(self._numbers(build.ARCHETYPES), [])
        for gone in ("ARCHETYPE_MIN", "archetype_minimums", "archetype_gate"):
            self.assertFalse(hasattr(build, gone), gone)
        self.assertFalse(hasattr(lv, "ARCHETYPE_GATE"))

    def test_minimum_sabotage(self):
        rows = [("vehicle", ("car",), "long and low (length 1.8-2.5 x the "
                 "width)")]
        self.assertEqual(len(self._numbers(rows)), 1)

    def test_note_lines(self):
        self.assertTrue(build.archetype_note("vehicle").startswith(
            "vehicle - long and low"))
        self.assertIn("a big head with a face",
                      build.archetype_note("robot or character"))
        self.assertTrue(build.archetype_note("lamp").startswith("lamp - "))
        self.assertIsNone(build.archetype_note(None))
        self.assertIsNone(build.archetype_note("spaceship"))

    def test_archetype_for(self):
        self.assertEqual(build.archetype_for("an alarm clock"), "clock")
        self.assertEqual(build.archetype_for("a desk fan"), "fan")
        self.assertEqual(build.archetype_for("a thing", "toy_car.py"), "vehicle")
        self.assertIsNone(build.archetype_for("a thing"))

    def test_note_only_on_levels_one_and_six_never_in_the_gate(self):
        note = build.archetype_note("handheld")
        for n in range(1, lv.COUNT + 1):
            for seed in (None, "handheld_console.py"):
                t = lv.level_text(n, seed=seed, archetype=note)
                with self.subTest(level=n, seed=seed):
                    self.assertEqual(note in t, n in (1, 6))
                    self.assertNotIn(note, t.split("\nGATE: ", 1)[1])
                    if n in (1, 6):
                        self.assertIn("- Design note (advisory, never a "
                                      "gate): " + note, _checklist(t))


class Prompt(_Mode):
    """R430: quality_prompt(seed=...) and its levels agree."""

    MODE = "quality"

    def _ladder(self, seed, arch=None):
        state = {"level": 1, "count": 9, "seed": seed}
        if arch:
            state["archetype"] = arch
        return state

    def test_seeded_prompt_and_levels_never_contradict(self):
        gate = build.archetype_note("vehicle")
        p = build.quality_prompt(WS, False, self._ladder("toy_car.py", gate),
                                 "toy_car.py")
        self.assertEqual(_contradictions(p), [])
        self.assertIn("model.py already holds examples/toy_car.py", p)
        self.assertIn("keep its hardware and fit code", _flat(p))
        self.assertIn(gate, p)
        # R510: no level minutes in the prompt (results, not time)
        self.assertNotIn("A level takes about", p)
        self.assertIn("a level is judged on its result, not its time",
                      _flat(p))
        self.assertIn("never start a later level's new work early", _flat(p))
        self.assertIn(build.untimed(lv.level_text(
            1, seed="toy_car.py", archetype=gate, **build._level_values())), p)
        # and every level the ladder sends after it
        ws = _ws(self)
        lv.write(ws, 1, "toy_car.py", gate)
        for n in range(2, lv.COUNT + 1):
            msg = build.next_level(ws)
            with self.subTest(level=n):
                self.assertEqual(_contradictions(msg), [])
                self.assertTrue(_checklist(msg).lower().startswith(HERO))

    def test_level_turn_prompt_keeps_the_seed(self):
        # start_levels returns no seed on a level turn; the ladder has it
        p = build.quality_prompt(WS, False, self._ladder("toy_car.py"), None)
        self.assertIn("model.py already holds examples/toy_car.py", p)
        self.assertEqual(_contradictions(p), [])

    def test_unseeded_prompt_keeps_its_level_one(self):
        p = build.quality_prompt(WS, False, self._ladder(None), None)
        self.assertIn(build.untimed(lv.level_text(1, **build._level_values())),
                      p)
        self.assertIn("No hollowing and no openings yet.", p)
        self.assertNotIn("A level takes about", p)         # R510
        self.assertIn("never start a later level's work early", _flat(p))

    def test_prompt_sabotage(self):
        check, gate = lv.SEEDED[1]
        saved = dict(lv.SEEDED)
        self.addCleanup(lambda: (lv.SEEDED.clear(), lv.SEEDED.update(saved)))
        lv.SEEDED[1] = (check + "\n  No hollowing and no openings yet.", gate)
        p = build.quality_prompt(WS, False, self._ladder("toy_car.py"),
                                 "toy_car.py")
        self.assertIn("no hollowing", _contradictions(p))

    def test_start_levels_records_the_archetype(self):
        for request, seed, want in (
                ("a toy car", "toy_car.py", "vehicle - "),
                ("a handheld game console", "handheld_console.py",
                 "handheld - "),
                ("an alarm clock", None, "clock - "),
                ("a bedside lamp", "bedside_lamp.py", "lamp - "),
                ("a phone holder", None, None)):
            ws = _ws(self)
            with self.subTest(request=request):
                ladder, got = build.start_levels(ws, request, True)
                if seed:
                    self.assertEqual(got, seed)
                arch = ladder.get("archetype")
                if want:
                    self.assertTrue(arch.startswith(want), arch)
                    lv_msg = build.next_level(ws)          # LEVEL 2: none
                    self.assertNotIn(arch, lv_msg)
                else:
                    self.assertNotIn("archetype", ladder)


if __name__ == "__main__":
    unittest.main()
