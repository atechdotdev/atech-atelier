"""board_look: the studio.atech.dev look of the board and modules.

Holds the measured facts the 3D look stands on, with plain Python + numpy
(no FreeCAD, no Qt; skipped without numpy):

  * every library part drawn by the look has its GLB in models/glb;
  * every GLB decodes (KHR_mesh_quantization, or plain float for the
    derived modules) and is the same size as the library STL every fit
    check measures;
  * models/SIMREADY.json (projects/import_simready.py) agrees with the files
    on disk, and only the modules without Atech CAD are derived;
  * OFFSETS_MM puts each GLB exactly on its STL (bounding-box minima agree);
  * the colour rules: linear -> sRGB, lit LEDs, clear glass, the unlit
    silkscreen, the textured screen and its UV transform.

The look in the real app (picking still selects the module, nothing saved
into the document, the screen art) was measured with the GUI; see the
module docstring.

    python -m unittest -v test_board_look
"""
import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
MODELS = os.path.join(REPO, "models")
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

try:
    import numpy as np
    from acadagent import board_look as bl
except ImportError:
    np = bl = None


def stl_points(path):
    """Vertices of a binary (or ASCII) STL, (n,3) float."""
    with open(path, "rb") as fh:
        b = fh.read()
    n = struct.unpack("<I", b[80:84])[0]
    if len(b) == 84 + 50 * n:
        rec = np.frombuffer(b, dtype=[("n", "<f4", (3,)), ("v", "<f4", (9,)),
                                      ("a", "<u2")], count=n, offset=84)
        return rec["v"].reshape(-1, 3).astype(float)
    pts = [list(map(float, ln.split()[1:4])) for ln in b.decode("ascii", "replace").splitlines()
           if ln.strip().startswith("vertex")]
    return np.array(pts, float)


def glb_points(path):
    data = bl.read_glb(path)
    return np.concatenate([pos[np.unique(tri)] for _m, pos, tri, _uv in data["prims"]])


@unittest.skipIf(bl is None, "numpy not installed")
class TestModels(unittest.TestCase):
    def test_every_part_has_its_glb(self):
        glb = os.path.join(MODELS, "glb")
        missing = [m for m in bl.SLUG if bl.glb_path(m, glb) is None]
        self.assertEqual(missing, [])

    def test_glbs_match_their_stls(self):
        glb = os.path.join(MODELS, "glb")
        for module, off in sorted(bl.OFFSETS_MM.items()):
            stl = os.path.join(MODELS, "stl", module + ".stl")
            if not os.path.isfile(stl):
                continue
            G = glb_points(bl.glb_path(module, glb)) + np.array(off)
            S = stl_points(stl)
            np.testing.assert_allclose(np.ptp(G, 0), np.ptp(S, 0), atol=0.15,
                                       err_msg="%s: GLB and STL sizes" % module)
            np.testing.assert_allclose(G.min(0), S.min(0), atol=0.15,
                                       err_msg="%s: offset puts the GLB off its STL" % module)

    def test_offsets_follow_one_rule(self):
        # Each GLB's origin (its connector, on the cell centre) lands at
        # x = 10 mm per port + 0.15, y = -2.54, z = 10.0 (+/- 0.13) in the
        # STL frame: import_simready.py writes the dataset STLs with this
        # rule, or with the old library frame (LIBRARY_FRAME: dc_motor,
        # speaker); usbc (v1.5, MEASURED) is 0.125 off in z. The speaker's
        # STL frame differs in y (its body hangs below the board plane). An
        # entry that breaks the rule is a red flag, not a tweak.
        glb = os.path.join(MODELS, "glb")
        for module, (x, y, z) in bl.OFFSETS_MM.items():
            w = np.ptp(glb_points(bl.glb_path(module, glb))[:, 0])
            ports = int(round(w / 20.0))
            self.assertAlmostEqual(x, 10.0 * ports + 0.15, delta=0.02, msg=module)
            self.assertAlmostEqual(z, 10.0, delta=0.13, msg=module)
            if module != "speaker":
                self.assertAlmostEqual(y, -2.54, delta=0.03, msg=module)

    def test_simready_record_matches_the_files(self):
        import hashlib
        import json
        with open(os.path.join(MODELS, "SIMREADY.json"), encoding="utf-8") as fh:
            rec = json.load(fh)

        def sha(p):
            with open(p, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        derived = set()
        for module, m in rec["modules"].items():
            self.assertEqual(bl.SLUG.get(module) + ".glb", m["glb"], module)
            self.assertEqual(sha(os.path.join(MODELS, "stl", module + ".stl")),
                             m["stl_sha256"], module)
            self.assertEqual(sha(os.path.join(MODELS, "glb", m["glb"])),
                             m["glb_sha256"], module)
            self.assertEqual(m["derived"], m["visual_source"].startswith("derived:"), module)
            if m["derived"]:
                derived.add(module)
        self.assertEqual(derived, {"pir", "scd40_air_quality", "robot_arm",
                                   "stepper_motor", "soil_sensor", "load_cell",
                                   "power_jack"})

    def test_board_hides_only_what_atech_ports_hides(self):
        import ast
        import re
        with open(os.path.join(REPO, "projects", "atech_ports.py"), encoding="utf-8") as fh:
            m = re.search(r"^HIDDEN_MATERIALS = (.+)$", fh.read(), re.M)
        self.assertIsNotNone(m, "atech_ports.HIDDEN_MATERIALS not found")
        self.assertEqual(tuple(ast.literal_eval(m.group(1))), bl.BOARD_HIDDEN)


@unittest.skipIf(bl is None, "numpy not installed")
class TestNoSharedNodes(unittest.TestCase):
    """The crash fix (2026-10-20): ONE cached Coin scene per part, hung under
    every object in every document, crashed the app on Close All / quit with
    2+ unsaved documents (a shared SoTexture2 outlived the GL contexts that
    used it). Only plain data may be cached; every object builds its own
    scene."""

    def test_cache_holds_plain_data_only(self):
        glb = bl.glb_path("screen", os.path.join(MODELS, "glb"))
        prep = bl.prepare(bl.read_glb(glb), (1, 2, 3))
        self.assertEqual(prep["offset"], (1.0, 2.0, 3.0))
        self.assertTrue(prep["parts"])
        for part in prep["parts"]:
            self.assertIsInstance(part["points"], list)
            self.assertIsInstance(part["index"], list)
            self.assertIn(part["png"].__class__, (bytes, type(None)))
            for v in part["look"].values():
                self.assertNotIn("pivy", type(v).__module__ or "")
        art = [p for p in prep["parts"] if p["png"] is not None]
        self.assertEqual(len(art), 1)                    # the screen art
        us = [u for u, _v in art[0]["uv"]]
        self.assertAlmostEqual(min(us), 0.0, places=2)
        self.assertAlmostEqual(max(us), 1.0, places=2)

    def test_no_module_level_coin_cache(self):
        with open(bl.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("_SCENES", src)
        self.assertNotIn(".ref()", src)                  # nothing pinned or shared
        self.assertIn("node = scene_for(mod)", src)      # built per object


@unittest.skipIf(bl is None, "numpy not installed")
class TestColour(unittest.TestCase):
    def test_srgb(self):
        self.assertAlmostEqual(bl.srgb(0.0), 0.0)
        self.assertAlmostEqual(bl.srgb(1.0), 1.0)
        self.assertAlmostEqual(bl.srgb(0.214), 0.5, delta=0.01)

    def test_led_glass_unlit_and_black(self):
        led = bl.coin_material({"pbrMetallicRoughness": {"baseColorFactor": [1, 0.02, 0.01, 1]},
                                "emissiveFactor": [1, 0.02, 0.01]})
        self.assertGreater(led["emissive"][0], 0.9)
        glass = bl.coin_material({"pbrMetallicRoughness": {"baseColorFactor": [0.86, 0.9, 0.93, 0.42]},
                                  "alphaMode": "BLEND",
                                  "extensions": {"KHR_materials_transmission": {}}})
        self.assertGreater(glass["transparency"], 0.3)
        silk = bl.coin_material({"pbrMetallicRoughness": {"baseColorFactor": [0.69, 0.69, 0.73, 1]},
                                 "extensions": {"KHR_materials_unlit": {}}})
        self.assertEqual(silk["diffuse"], (0, 0, 0))
        self.assertGreater(min(silk["emissive"]), 0.8)
        black = bl.coin_material({"pbrMetallicRoughness": {"baseColorFactor": [0.003, 0.004, 0.004, 1]}})
        self.assertGreaterEqual(min(black["diffuse"]), 0.2)      # charcoal, not a hole

    def test_screen_art_is_self_lit_with_its_uv_transform(self):
        glb = bl.glb_path("screen", os.path.join(MODELS, "glb"))
        data = bl.read_glb(glb)
        art = [(m, uv) for mi, _p, _t, uv in data["prims"]
               for m in [data["materials"][mi]] if m.get("name") == "screen_art"]
        self.assertEqual(len(art), 1)
        m, uv = art[0]
        look = bl.coin_material(m)
        self.assertIsNotNone(look["texture"])
        self.assertEqual(look["emissive"], (1, 1, 1))
        self.assertIsNotNone(bl._texture_bytes(data, look["texture"]))
        uvt = bl.uv_transformed(uv, look["uv_transform"])
        # MEASURED: quantized UVs times the transform's 16.0037 span 0..1
        self.assertAlmostEqual(float(uvt.min()), 0.0, places=2)
        self.assertAlmostEqual(float(uvt.max()), 1.0, places=2)

    def test_uv_transform_order(self):
        uv = np.array([[0.5, 0.25]])
        out = bl.uv_transformed(uv, {"scale": [2, 4], "offset": [0.1, 0.2]})
        np.testing.assert_allclose(out, [[1.1, 1.2]])


if __name__ == "__main__":
    unittest.main()
