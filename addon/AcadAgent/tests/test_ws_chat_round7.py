"""WS-CHAT round 7, headless against the REAL AgentPanel (same fakes as
test_ws_chat_panel / round5 / round6): R158 ("Add view" on an Atech board
looks at the module face, as "Ask about this view" does since R145), R159
(a chat capture puts the user's camera back), S51 panel half (a first Atech
preview whose only failure is a slide path closed by a cap not yet declared
fitted_after is "in progress"; the end of the turn still fails it).

R158/R159 were also measured in a real Studio, offscreen (dist/test-root,
whose AcadAgent links this repo; QT_QPA_PLATFORM=offscreen, isolated HOME;
board + Light seated on port 3 with atech_ports.seat, the Light coloured
#ff00ff; pixels r>120, b>120, g<90, 1 in 9 sampled of 1200x900; user camera
isometric + fitAll): capture_to_panel(stub) with its default view ->
"Module face" (caption "Mods - Module face view"), 1 180 of 120 000
magenta; capture(view_name="Isometric") 0 of 120 000. Camera after each
capture vs the user's, max numeric difference over the camera fields:
1.26e-06 (float round trip of the orientation) with the restore; 69.6 with
restore=False.

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_round7.py -v
"""
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)
import test_ws_chat_panel as twp  # noqa: E402
import test_ws_chat_round5 as tr5  # noqa: E402

from acadagent import build, capture, panel, vision  # noqa: E402

wait_until = tcr.wait_until
_Doc, _Obj = twp._Doc, twp._Obj


class _FakeViewport(object):
    """acadagent.viewport stand-in: the module face and look_from."""

    def install(self, case, face=(0.6, 1.0, 0.5)):
        import acadagent
        vp = types.ModuleType("acadagent.viewport")
        vp.face = face
        vp.looks = []
        vp.module_face_direction = lambda doc: vp.face
        vp.look_from = lambda x, y, z, v=None: \
            vp.looks.append(((x, y, z), v)) or True
        saved = sys.modules.get("acadagent.viewport")
        had, old = hasattr(acadagent, "viewport"), \
            getattr(acadagent, "viewport", None)
        sys.modules["acadagent.viewport"] = vp
        acadagent.viewport = vp

        def restore():
            if saved is not None:
                sys.modules["acadagent.viewport"] = saved
            else:
                sys.modules.pop("acadagent.viewport", None)
            if had:
                acadagent.viewport = old
            else:
                delattr(acadagent, "viewport")
        case.addCleanup(restore)
        return vp


class _CamView(tr5._View):
    """A view with a camera: turns and fits change it, like FreeCAD's."""

    def __init__(self, fail_save=False):
        super().__init__(fail_save)
        self.camera = "#Inventor V2.1 ascii\nOrthographicCamera { user }"
        self.saved_camera = None

    def getCamera(self):                                # noqa: N802
        self.calls.append(("get", self.anim))
        return self.camera

    def setCamera(self, cam):                           # noqa: N802
        self.calls.append(("set", self.anim))
        self.camera = cam

    def viewIsometric(self):                            # noqa: N802
        super().viewIsometric()
        self.camera = "iso"

    def fitAll(self):                                   # noqa: N802
        super().fitAll()
        self.camera += " fitted"

    def saveImage(self, path, w, h, bg):                # noqa: N802
        self.saved_camera = self.camera
        super().saveImage(path, w, h, bg)


class _GuiCase(twp.Case):

    def gui(self, view):
        gui = types.ModuleType("FreeCADGui")
        gui.ActiveDocument = types.SimpleNamespace(ActiveView=view)
        saved = sys.modules.get("FreeCADGui")
        sys.modules["FreeCADGui"] = gui
        self.addCleanup(lambda: sys.modules.__setitem__("FreeCADGui", saved)
                        if saved else sys.modules.pop("FreeCADGui", None))


# ------------------------------------------------------------------ R158
class TestR158AddView(_GuiCase):

    def _record_c2p(self):
        asked = []

        def fake_c2p(p, view_name=capture.AUTO, **_k):
            asked.append(view_name)
            return None
        self.patch(capture, "capture_to_panel", fake_c2p)
        return asked

    def test_r158_add_view_on_a_board_asks_for_the_module_face(self):
        self.fc.add(tr5._board(modules=[("light", (3,))]))
        asked = self._record_c2p()
        self.p._on_capture()
        self.assertEqual(asked, [capture.MODULE_FACE])

    def test_r158_add_view_elsewhere_stays_isometric(self):
        self.fc.add(_Doc("Part", "uid-p", [_Obj("Body")]))
        asked = self._record_c2p()
        self.p._on_capture()
        self.assertEqual(asked, ["Isometric"])

    def test_r158_capture_to_panel_default_is_the_documents_view(self):
        """commands.py's Add-view command calls capture_to_panel(panel)
        with no view: the default must follow the document too."""
        _FakeViewport().install(self)
        self.fc.add(tr5._board(modules=[("light", (3,))]))
        v = _CamView()
        self.gui(v)
        shots = []
        stub = types.SimpleNamespace(
            capture_path=lambda: os.path.join(self.tmp, "a.png"),
            add_shot=lambda path, cap: shots.append((path, cap)))
        path = capture.capture_to_panel(stub)
        self.assertEqual(path, os.path.join(self.tmp, "a.png"))
        self.assertNotIn("iso", [c[0] for c in v.calls])
        self.assertIn("Module face view", shots[0][1])
        self.assertEqual(capture.default_view(), capture.MODULE_FACE)
        self.fc.add(_Doc("Part", "uid-p", [_Obj("Body")]))
        self.assertEqual(capture.default_view(), "Isometric")
        print("\n  [R158] board: %r; plain part: %r"
              % (shots[0][1].split(" - ")[1], capture.default_view()))


# ------------------------------------------------------------------ R159
class TestR159CameraRestored(_GuiCase):

    def test_r159_the_users_camera_comes_back(self):
        v = _CamView()
        self.gui(v)
        user = v.camera
        capture.capture(path=os.path.join(self.tmp, "c.png"))
        self.assertEqual(v.saved_camera, "iso fitted",
                         "the picture is still the turned, fitted view")
        self.assertEqual(v.camera, user, "the live camera is the user's")
        kinds = [c[0] for c in v.calls]
        self.assertEqual(kinds, ["stop", "get", "iso", "fit", "save", "set"])
        # Put back while animations are still off: not animated either.
        self.assertTrue(all(not on for _k, on in v.calls), v.calls)
        self.assertTrue(v.anim)
        print("\n  [R159] calls %s; camera after = user's" % kinds)

    def test_r159_restored_when_the_save_fails(self):
        v = _CamView(fail_save=True)
        self.gui(v)
        user = v.camera
        with self.assertRaises(capture.CaptureError):
            capture.capture(path=os.path.join(self.tmp, "x.png"))
        self.assertEqual(v.camera, user)

    def test_r159_restore_false_keeps_the_capture_camera(self):
        v = _CamView()
        self.gui(v)
        capture.capture(path=os.path.join(self.tmp, "k.png"), restore=False)
        self.assertEqual(v.camera, "iso fitted")

    def test_r159_view_without_a_camera_api_still_captures(self):
        v = tr5._View()                  # no getCamera / setCamera
        self.gui(v)
        path = os.path.join(self.tmp, "n.png")
        self.assertEqual(capture.capture(path=path), path)

    def test_r159_module_face_capture_restores_too(self):
        vp = _FakeViewport().install(self)
        self.fc.add(tr5._board(modules=[("light", (3,))]))
        v = _CamView()
        self.gui(v)
        user = v.camera
        capture.capture(path=os.path.join(self.tmp, "m.png"),
                        view_name=capture.MODULE_FACE)
        self.assertEqual(len(vp.looks), 1)
        self.assertEqual(v.camera, user)


# ------------------------------------------------------------------- S51
def _atech_result(verdicts, design_part=True):
    """A preview of a closed Atech case: board + Light, and the case body
    unless design_part is False. atech_checked: verdicts from the child."""
    ms = [{"name": "motherboard", "label": "motherboard", "solids": 1,
           "volume_mm3": 1.0, "bbox_bound": [1, 1, 1]},
          {"name": "light_p3", "label": "light_p3", "solids": 1,
           "volume_mm3": 1.0, "bbox_bound": [1, 1, 1]}]
    if design_part:
        ms.append({"name": "Case", "label": "Case", "solids": 1,
                   "volume_mm3": 1000.0, "bbox_bound": [60, 40, 30]})
    r = build.Result(True, "model.py", created=[m["name"] for m in ms],
                     measurements=ms, doc="Mods")
    r.atech_verdicts = {"light_p3": dict(verdicts)}
    r.atech_checked = True
    return r


SLIDE_FAIL = {"seated": "PASS", "interference": "PASS", "slide_path": "FAIL"}


class TestS51UndeclaredCaps(twp.Round3):

    def _doc(self):
        d = tr5._board(modules=[("light", (3,))])
        d.Objects.append(_Obj("Case"))
        return self.fc.add(d)

    def _intent(self, st, data):
        with open(os.path.join(st.ws, build.INTENT), "w",
                  encoding="utf-8") as fh:
            json.dump(data, fh)

    def test_s51_undeclared_cap_preview_is_in_progress(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        failed0 = self.p.stats["previews_failed"]
        self.p._settle(st, _atech_result(SLIDE_FAIL), True, "h1")
        card = self.p._build_card
        self.assertEqual(card.status.text(), "preview: in progress")
        self.assertEqual(card.status.objectName(), "StatusIdle")
        self.assertIn("not yet declared as fitted after", card.body.text())
        self.assertEqual(self.p.stats["previews_failed"], failed0)
        self.assertEqual(self.p._preview_error, "")
        print("\n  [S51] no intent.json: %r" % card.status.text())

    def test_s51_intent_without_fitted_after_is_still_in_progress(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        self._intent(st, {"board": "upright"})
        self.p._settle(st, _atech_result(SLIDE_FAIL), True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: in progress")

    def test_s51_declared_fitted_after_that_still_fails_is_red(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        self._intent(st, {"fitted_after": ["End_Cap_L", "End_Cap_R"]})
        self.p._settle(st, _atech_result(SLIDE_FAIL), True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: check failed")
        self.assertIn("slide_path FAIL", self.p._preview_error)

    def test_s51_unreadable_intent_is_not_undeclared(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        with open(os.path.join(st.ws, build.INTENT), "w") as fh:
            fh.write("{not json")
        self.p._settle(st, _atech_result(SLIDE_FAIL), True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: check failed")

    def test_s51_another_atech_fail_is_red(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        v = dict(SLIDE_FAIL, seated="FAIL")
        self.p._settle(st, _atech_result(v), True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: check failed")

    def test_s51_no_design_part_no_cap_is_red(self):
        """Only the board and the module: nothing that could be a cap, so
        a closed slide path is not the draft's caps."""
        self.viewport()
        d = self.fc.add(tr5._board(modules=[("light", (3,))]))
        st = self.turn_state(key="uid-mods", doc=d)
        self.p._settle(st, _atech_result(SLIDE_FAIL, design_part=False),
                       True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: check failed")

    def test_s51_with_intent_misses_too(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        r = _atech_result(SLIDE_FAIL)
        r.intent_problems = ["overall size: you intended 60 mm, Atelier "
                             "measured 50 mm"]
        self.p._settle(st, r, True, "h1")
        body = self.p._build_card.body.text()
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: in progress")
        self.assertIn("intent.json targets", body)
        self.assertIn("fitted after", body)

    def test_s51_a_real_problem_beside_it_is_red(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        r = _atech_result(SLIDE_FAIL)
        r.measurements[2] = dict(r.measurements[2], valid=False)
        self.p._settle(st, r, True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: check failed")

    def test_s51_reads_the_results_own_workspace(self):
        """The build's workspace declares fitted_after; the current turn's
        does not. The result's own intent decides (red)."""
        import tempfile
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        other = tempfile.mkdtemp()
        with open(os.path.join(other, build.INTENT), "w",
                  encoding="utf-8") as fh:
            json.dump({"fitted_after": ["End_Cap_L"]}, fh)
        r = _atech_result(SLIDE_FAIL)
        r.workspace = other
        self.p._settle(st, r, True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: check failed")

    def test_s51_kit_without_fitted_after_is_red(self):
        """A ./check that does not read fitted_after: the prompt says leave
        slide paths open, so a closed one is a real failure."""
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        self.patch(build, "kit_reads_fitted_after", lambda: False)
        self.p._settle(st, _atech_result(SLIDE_FAIL), True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: check failed")

    def test_s51_final_build_still_fails(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        r = _atech_result(SLIDE_FAIL)
        self.p._settle(st, r, False, "h1")
        self.assertEqual(self.p._build_card.status.text(), "check failed")

    def test_s51_end_of_turn_still_fails_the_turn(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        self.script(st)
        self.verdicts = {"light_p3": dict(SLIDE_FAIL)}
        jobs = []

        def start(*a, **k):
            jobs.append((a, k))
            return build.PendingBuild(_atech_result(SLIDE_FAIL))
        self.patch(build, "start", start)
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._run_build(["model.py"], preview=True)
        self.assertTrue(wait_until(lambda: self.p._pending is None, 3))
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: in progress")
        self.p._applied = build.snapshot(st.ws)
        self.p._on_claude_done("Built the case.", {})
        self.assertTrue(self.idle(5))
        self.assertEqual(len(jobs), 1, "the unchanged script was rebuilt")
        self.assertEqual(self.p._build_card.status.text(), "check failed")
        self.assertEqual(len(sent), 1)
        self.assertIn("slide_path FAIL", sent[0])
        print("\n  [S51] preview 'preview: in progress'; end of turn "
              "'check failed', fix sent (%d build)" % len(jobs))


if __name__ == "__main__":
    unittest.main()
