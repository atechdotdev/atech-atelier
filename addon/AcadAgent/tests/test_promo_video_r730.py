"""R730: the assembly / promo video (acadagent/promo/, promo_video.py).

No FreeCAD: a synthetic product of boxes (a board, two modules, a cable,
printed parts, screws). Needs numpy and PIL (the bundled Python has both);
skips without them.

    <bundled python> -m unittest -v test_promo_video_r730
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(HERE, "..", "acadagent"))
PROMO = os.path.join(PKG, "promo")
for p in (PROMO, os.path.join(PKG, "agent_kit"), os.path.dirname(PKG)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import numpy as np
    import PIL  # noqa: F401
    HAVE = True
except ImportError:                                       # pragma: no cover
    HAVE = False

import mux  # noqa: E402


def box(lo, hi):
    """(T, N) of an axis-aligned box: 12 triangles."""
    import numpy as np
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    quads = [(0, 3, 2, 1, (0, 0, -1)), (4, 5, 6, 7, (0, 0, 1)), (0, 1, 5, 4, (0, -1, 0)),
             (2, 3, 7, 6, (0, 1, 0)), (1, 2, 6, 5, (1, 0, 0)), (3, 0, 4, 7, (-1, 0, 0))]
    T, N = [], []
    for a, b, c, d, n in quads:
        T += [[v[a], v[b], v[c]], [v[a], v[c], v[d]]]
        N += [[n] * 3, [n] * 3]
    return np.array(T), np.array(N, float)


def product():
    """(records, tris) of a small boxy product."""
    recs, tris = [], []

    def add(rec, lo, hi):
        recs.append(rec)
        tris.append(box(lo, hi))
    add({"label": "Lid", "kind": "body", "color": [0.9, 0.4, 0.3]}, (0, 0, 20), (60, 40, 24))
    add({"label": "Screw_2", "kind": "body", "color": [0.8, 0.8, 0.8]}, (4, 4, -6), (6, 6, 2))
    add({"label": "Base", "kind": "body", "color": [0.3, 0.3, 0.3]}, (0, 0, 0), (60, 40, 4))
    add({"label": "Shell", "kind": "body", "color": [0.4, 0.8, 0.7]}, (0, 0, 4), (60, 40, 20))
    add({"label": "Screw_1", "kind": "body", "color": [0.8, 0.8, 0.8]}, (54, 4, -6), (56, 6, 2))
    add({"label": "light_p14", "kind": "module", "name": "Light", "ports": [14],
         "slide_axis": [-1, 0, 0], "slide_out": 12.0, "color": [0.3, 0.3, 0.3]},
        (40, 10, 8), (48, 18, 14))
    add({"label": "button_p6", "kind": "module", "name": "Button", "ports": [6],
         "slide_axis": [1, 0, 0], "slide_out": 12.0, "color": [0.3, 0.3, 0.3]},
        (10, 10, 8), (18, 18, 14))
    add({"label": "motherboard", "kind": "board", "name": "Atech board",
         "color": [0.16, 0.17, 0.2]}, (5, 5, 5), (55, 35, 8))
    add({"label": "motor_cable", "kind": "cable", "cable_of": "button_p6", "cable_to": "Button",
         "color": [0.85, 0.85, 0.82]}, (20, 18, 6), (22, 20, 18))
    return recs, tris


def scene_and_plan(spec=None, fitted_after=("Shell", "Lid")):
    import numpy as np
    import render
    import timeline
    recs, tris = product()
    T = np.concatenate([t for t, _n in tris])
    N = np.concatenate([n for _t, n in tris])
    starts = np.cumsum([0] + [len(t) for t, _n in tris])
    sc = render.Scene(recs, T, N, starts)
    plan = timeline.Plan(sc, spec or {"title": "Box"}, {"fitted_after": list(fitted_after)}, fps=12)
    return sc, plan


class Mux(unittest.TestCase):
    def test_mov_atoms_and_sample_table(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        frames = []
        for i in range(5):
            p = os.path.join(d, "%05d.jpg" % i)
            with open(p, "wb") as fh:
                fh.write(b"\xff\xd8" + bytes([i]) * (100 + i) + b"\xff\xd9")
            frames.append(p)
        out = mux.write_mov(frames, 24, os.path.join(d, "m.mov"), 64, 36)
        with open(out, "rb") as fh:
            data = fh.read()
        kinds, pos = [], 0
        while pos < len(data):
            size, kind = struct.unpack(">I4s", data[pos:pos + 8])
            kinds.append(kind)
            pos += size
        self.assertEqual(kinds, [b"ftyp", b"mdat", b"moov"])
        self.assertEqual(pos, len(data))
        i = data.index(b"stsz")
        _vf, _fixed, n = struct.unpack(">III", data[i + 4:i + 16])
        sizes = struct.unpack(">5I", data[i + 16:i + 36])
        self.assertEqual(n, 5)
        self.assertEqual(list(sizes), [os.path.getsize(f) for f in frames])
        i = data.index(b"stco")
        offs = struct.unpack(">5I", data[i + 12:i + 32])
        self.assertEqual(data[offs[3]:offs[3] + 2], b"\xff\xd8")     # each points at its JPEG
        self.assertIn(b"jpeg", data[data.index(b"stsd"):])

    @unittest.skipUnless(mux.find_ffmpeg(), "no ffmpeg here")
    def test_ffmpeg_reads_the_mov(self):
        if not HAVE:
            self.skipTest("numpy / PIL")
        from PIL import Image
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        frames = []
        for i in range(6):
            p = os.path.join(d, "%05d.jpg" % i)
            Image.new("RGB", (64, 36), (i * 40, 20, 90)).save(p, quality=90)
            frames.append(p)
        out = mux.write_mov(frames, 12, os.path.join(d, "m.mov"), 64, 36)
        p = subprocess.run([mux.find_ffmpeg(), "-v", "error", "-i", out, "-f", "null", "-"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


@unittest.skipUnless(HAVE, "numpy and PIL")
class Director(unittest.TestCase):
    def setUp(self):
        import director
        self.d = director
        self.parts = product()[0]

    def test_defaults_pick_a_stage_from_the_name(self):
        ctx = {"title": "mini_arcade"}
        self.assertEqual(self.d.defaults(ctx, self.parts)["environment"], "neon")
        self.assertEqual(self.d.defaults({"title": "Plant pot"}, self.parts)["environment"],
                         "garden")
        self.assertEqual(self.d.defaults({"title": "Thing"}, self.parts)["environment"], "studio")
        sp = self.d.defaults({"title": "Thing"}, self.parts)
        self.assertIn("Light", sp["tagline"])
        self.assertEqual(sp["accent"], "#e5664c")          # the lid: the most colourful part

    def test_merge_keeps_only_valid_fields(self):
        base = self.d.defaults({"title": "Box"}, self.parts)
        got = self.d.parse('Sure!\n{"title": "Boxy", "environment": "moon base", '
                           '"accent": "red", "hero_az": 300, '
                           '"captions": {"Lid": "Snaps on", "Nope": "x"}, '
                           '"spin": [{"part": "Lid", "axis": "z"}, {"part": "Ghost"}], '
                           '"glow": "all"}\nEnjoy')
        out = self.d.merge(base, got, self.parts)
        self.assertEqual(out["title"], "Boxy")
        self.assertEqual(out["environment"], base["environment"])  # unknown stage: kept
        self.assertEqual(out["accent"], base["accent"])            # not a colour: kept
        self.assertEqual(out["hero_az"], base["hero_az"])          # out of range: kept
        self.assertEqual(out["captions"], {"Lid": "Snaps on"})
        self.assertEqual(out["spin"], [{"part": "Lid", "axis": "z"}])
        self.assertIsNone(out["glow"])
        self.assertEqual(out["source"], "claude")

    def test_direct_falls_back_when_claude_fails(self):
        ctx = {"title": "Box", "director_argv": [sys.executable, "-c", "import sys; sys.exit(3)"]}
        self.assertEqual(self.d.direct(ctx, self.parts)["source"], "defaults")
        reply = json.dumps({"result": json.dumps({"title": "From Claude",
                                                  "environment": "night"})})
        ctx["director_argv"] = [sys.executable, "-c", "import sys; sys.stdin.read(); "
                                "print(%r)" % reply]
        sp = self.d.direct(ctx, self.parts)
        self.assertEqual((sp["title"], sp["environment"], sp["source"]),
                         ("From Claude", "night", "claude"))

    def test_prompt_lists_parts_and_stages(self):
        text = self.d.prompt({"title": "Box", "request": "a box with a light"}, self.parts)
        for word in ("light_p14", "port 14", "neon", "a box with a light"):
            self.assertIn(word, text)


@unittest.skipUnless(HAVE, "numpy and PIL")
class Timeline(unittest.TestCase):
    def test_order_electronics_then_body_then_screws(self):
        sc, plan = scene_and_plan()
        labels = [[sc.parts[k]["label"] for k in s.parts] for s in plan.steps]
        self.assertEqual(labels, [["motherboard"], ["button_p6"], ["light_p14"], ["motor_cable"],
                                  ["Base"], ["Shell"], ["Lid"], ["Screw_2", "Screw_1"]])
        self.assertEqual([s.kind for s in plan.steps],
                         ["drop", "slide", "slide", "grow", "fly", "fly", "fly", "screw"])
        self.assertEqual([s.chapter for s in plan.steps if s.chapter],
                         ["Electronics", "Body", "Fasteners"])
        self.assertEqual(plan.steps[1].sub, "Port 6")
        self.assertIn("x2", plan.steps[-1].title)

    def test_modules_slide_along_their_own_axis(self):
        sc, plan = scene_and_plan()
        k = [i for i, p in enumerate(sc.parts) if p["label"] == "light_p14"][0]
        off = plan.away[k]
        self.assertGreater(off[0], 0)            # inserted along -X: starts on +X
        self.assertAlmostEqual(off[1], 0)
        self.assertAlmostEqual(off[2], 0)

    def test_phases(self):
        sc, plan = scene_and_plan()
        n = len(sc.parts)
        hero = plan.state(1)
        self.assertEqual(hero["phase"], "hero")
        self.assertFalse(any(x.get("hidden") for x in hero["xf"].values()))
        gap = plan.state(int((plan.t_asm0 - 0.05) * plan.fps))
        self.assertEqual(gap["phase"], "gap")
        self.assertEqual(sum(1 for x in gap["xf"].values() if x.get("hidden")), n)
        # during the first body step the screws are not there yet, the board is home
        body = [s for s in plan.steps if s.kind == "fly"][0]
        st = plan.state(int((body.t0 + 0.05) * plan.fps) + 1)
        board = [i for i, p in enumerate(sc.parts) if p["kind"] == "board"][0]
        screws = [i for i, p in enumerate(sc.parts) if p["label"].startswith("Screw")]
        self.assertNotIn(board, st["xf"])
        self.assertTrue(all(st["xf"][k].get("hidden") for k in screws))
        self.assertEqual(st["step"][1], body)
        last = plan.state(plan.frames - 1)
        self.assertEqual(last["phase"], "finale")
        self.assertGreater(last["end"], 0.99)
        self.assertFalse(any(x.get("hidden") or x.get("t") is not None
                             for x in last["xf"].values()))
        self.assertGreater(plan.frames, plan.fps * 15)

    def test_spec_spin_and_glow(self):
        sc, plan = scene_and_plan({"spin": [{"part": "lid", "axis": "z", "speed": 2}],
                                   "glow": [{"part": "Shell", "color": "#00ff00"}]})
        lid = [i for i, p in enumerate(sc.parts) if p["label"] == "Lid"][0]
        shell = [i for i, p in enumerate(sc.parts) if p["label"] == "Shell"][0]
        self.assertEqual(list(plan.spin), [lid])
        self.assertEqual(plan.glow[shell], (0.0, 1.0, 0.0))
        st = plan.state(plan.frames - 5)
        self.assertIsNotNone(st["xf"][lid].get("R"))
        self.assertGreater(st["glow"][shell][1], 0.5)


@unittest.skipUnless(HAVE, "numpy and PIL")
class Render(unittest.TestCase):
    def test_every_stage_draws_the_product(self):
        import numpy as np
        import render
        import stage
        sc, plan = scene_and_plan()
        for name in stage.ENVIRONMENTS:
            env = stage.environment(name)
            cam = render.camera(sc, 30, 25, 1.2)
            img = render.render(sc, {}, cam, env, 96, 54, 1)
            self.assertEqual(img.shape, (54, 96, 3), name)
            self.assertTrue(np.isfinite(img).all(), name)
            empty = render.render(sc, {k: {"hidden": True} for k in range(len(sc.parts))},
                                  cam, env, 96, 54, 1)
            self.assertGreater(float(np.abs(img - empty).mean()), 0.01, name)


@unittest.skipUnless(HAVE, "numpy and PIL")
class Job(unittest.TestCase):
    def test_tiny_job_end_to_end(self):
        from acadagent import promo_video as pv
        job = tempfile.mkdtemp(prefix="atech-video-test-")
        self.addCleanup(shutil.rmtree, job, True)
        recs, tris = product()
        self.assertEqual(pv.write_job(job, recs, tris), len(recs))
        ctx = {"title": "Tiny box", "size": [96, 54], "supersample": 1, "fps": 4,
               "workers": 2, "interpreter": [sys.executable],
               "out_base": os.path.join(job, "tiny")}
        with open(os.path.join(job, "context.json"), "w") as fh:
            json.dump(ctx, fh)
        p = subprocess.run([sys.executable, os.path.join(PROMO, "job.py"), job],
                           capture_output=True, text=True, timeout=600)
        with open(os.path.join(job, "result.json")) as fh:
            res = json.load(fh)
        self.assertTrue(res.get("ok"), res.get("error") or p.stderr)
        self.assertTrue(os.path.getsize(res["path"]) > 1000)
        self.assertTrue(res["path"].endswith((".mp4", ".mov")))
        self.assertEqual(res["styled_by"], "defaults")
        self.assertFalse(os.path.isdir(os.path.join(job, "frames")))   # cleaned up


class Settings(unittest.TestCase):
    def test_on_by_default(self):
        from acadagent import settings
        self.assertIs(settings.DEFAULTS["assembly_video"], True)
        self.assertIs(settings.DEFAULTS["assembly_video_claude"], True)


if __name__ == "__main__":
    unittest.main()
