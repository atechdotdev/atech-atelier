"""R740: gears must really mesh (agent_kit/atech_gears.py, cad.mesh_phase).

    cd addon/AcadAgent/tests && python3 -m unittest test_gears_r740

Each case builds real cad.spur_gear geometry in freecadcmd and asserts the
probe's verdict: a phased pair turns clear, out of phase / too close / too
far / two modules fail, shifted pinions pass at the exact centre distance,
teeth against a smooth surface fail (the R740 RC tank), a bore needs a
shaft, a lone gear and a tyre tread are no problems. Skips without
freecadcmd (set ATECH_FREECADCMD).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import sandbox  # noqa: E402

KIT = sandbox.KIT_DIR
FC = sandbox.find_freecadcmd()

SCRIPT = r'''
import json, sys
sys.path.insert(0, %(kit)r)
import Part, atech_cad as cad, atech_gears as G
from FreeCAD import Vector as V

def gear(m, z, x=0.0, rot=0.0, bore=None, t=5.0, shift=0.0):
    g = cad.spur_gear(m, z, t, bore=bore, shift=shift)
    if rot:
        g.rotate(V(0, 0, 0), V(0, 0, 1), rot)
    g.translate(V(x, 0, 0))
    return g

def phased(m, za, zb, xa=0.0, xb=0.0):
    a = G.centre_distance(m, za, zb, xa + xb)
    A = cad.mesh_phase(gear(m, za, shift=xa), (0, 0, 0), "+Z", (1, 0, 0), tooth=True)
    B = cad.mesh_phase(gear(m, zb, a, shift=xb), (a, 0, 0), "+Z", (-1, 0, 0))
    return [("A", A), ("B", B)]

a = 1.5 * (18 + 12) / 2
smooth = Part.makeCylinder(20, 5).cut(Part.makeCylinder(15.3, 5))
# a tyre with 40 square tread grooves: evenly spaced, but no involute teeth
tread = cad.cut(Part.makeCylinder(30, 8),
                [Part.makeBox(3, 4, 8, V(28.5, -2, 0)).rotated(V(0, 0, 0), V(0, 0, 1), k * 9)
                 for k in range(40)])
cases = {
    "phased": phased(1.5, 18, 12),
    "unphased": [("A", gear(1.5, 18)), ("B", gear(1.5, 12, a))],
    "close": [("A", gear(1.5, 18)), ("B", gear(1.5, 12, a - 0.6, rot=15))],
    "far": [("A", gear(1.5, 18)), ("B", gear(1.5, 12, a + 0.8, rot=15))],
    "modules": [("A", gear(1.5, 18)), ("B", gear(1.25, 14, 1.5 * 9 + 1.25 * 8))],
    "shifted": phased(1.25, 9, 40, cad.gear_shift_for(9), 0.0),
    "undercut": phased(1.25, 9, 40),
    "smooth": [("A", gear(1.5, 18)), ("Belt", smooth)],
    "empty_bore": [("A", gear(1.5, 18, bore=3)), ("B", gear(1.5, 12, a, bore=3, rot=15))],
    "lone": [("A", gear(1.5, 24, bore=8))],
    "tread": [("Tyre", tread)],
}
out = {}
for k, parts in cases.items():
    rows, bad, notes = G.gear_probe([{"label": l, "shape": s} for l, s in parts])
    out[k] = {"rows": [{kk: vv for kk, vv in r.items() if kk != "module"} for r in rows],
              "bad": bad, "notes": notes}
print("GEARS=" + json.dumps(out))
'''


@unittest.skipIf(FC is None, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
class GearProbe(unittest.TestCase):
    res = None

    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp(prefix="atech-gears-")
        path = os.path.join(d, "gears.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(SCRIPT % {"kit": KIT})
        p = subprocess.run([FC, path], capture_output=True, text=True, timeout=600, cwd=d)
        out = p.stdout + p.stderr
        for line in out.splitlines():
            if line.startswith("GEARS="):
                cls.res = json.loads(line[len("GEARS="):])
        cls.out = out

    def case(self, k):
        self.assertIsNotNone(self.res, self.out[-3000:])
        return self.res[k]

    def pair(self, k):
        return [r for r in self.case(k)["rows"] if "gears" in r][0]

    def test_phased_pair_turns(self):
        self.assertEqual(self.case("phased")["bad"], [])
        self.assertTrue(self.pair("phased")["turns"])

    def test_unphased_pair_says_how_far_to_turn(self):
        bad = self.case("unphased")["bad"]
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("overlap as built", bad[0])
        self.assertAlmostEqual(self.pair("unphased")["turn_by_deg"], 15.0, places=1)

    def test_centre_distance(self):
        self.assertIn("too close", " ".join(self.case("close")["bad"]))
        self.assertIn("too far", " ".join(self.case("far")["bad"]))
        self.assertAlmostEqual(self.pair("close")["centre_needed_mm"], 22.5, places=2)

    def test_two_modules(self):
        bad = self.case("modules")["bad"]
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("same module", bad[0])

    def test_shifted_pinion_meshes_undercut_binds(self):
        self.assertEqual(self.case("shifted")["bad"], [])
        self.assertTrue(self.pair("shifted")["turns"])
        self.assertIn("bind at every phase", " ".join(self.case("undercut")["bad"]))

    def test_smooth_surface_is_driven_by_nothing(self):
        bad = self.case("smooth")["bad"]
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("smooth surface of Belt", bad[0])

    def test_bore_needs_a_shaft(self):
        bad = self.case("empty_bore")["bad"]
        self.assertEqual(sum("bore" in b for b in bad), 2, bad)

    def test_lone_gear_and_tread_are_fine(self):
        self.assertEqual(self.case("lone")["bad"], [])
        self.assertTrue(any("stands alone" in n for n in self.case("lone")["notes"]))
        self.assertEqual(self.case("tread")["rows"], [])


if __name__ == "__main__":
    unittest.main()
