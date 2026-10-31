"""R723: the wireframe ("skeleton") view keeps Atech hardware solid.

  viewport.wireframe_plan: every part that can be a wireframe becomes one,
  except the Atech board, modules and cables, which stay solid so they can
  be seen inside the case. (The real FreeCAD run, display modes and the
  modified flag, was measured in the offscreen app: Case -> Wireframe,
  Board and cable keep Flat Lines, Modified stays False, off restores.)

    python -m unittest -v test_wireframe_r723
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)
for _m in ("FreeCAD", "FreeCADGui"):          # plain Python: stubs suffice
    sys.modules.setdefault(_m, types.ModuleType(_m))


class _VO:
    def __init__(self, modes=("Flat Lines", "Shaded", "Wireframe", "Points")):
        self._m = list(modes)

    def listDisplayModes(self):                        # noqa: N802
        return self._m


class _Obj:
    def __init__(self, name, vo=None, **props):
        self.Name = name
        self.ViewObject = vo if vo is not None else _VO()
        for k, v in props.items():
            setattr(self, k, v)


class TestPlan(unittest.TestCase):
    def test_hardware_stays_solid(self):
        from acadagent import viewport
        objs = [_Obj("Case"),
                _Obj("Board", AtechRole="board"),
                _Obj("Light", AtechRole="module"),
                _Obj("Lib", AtechModule="light_6"),
                _Obj("light_cable_p6", AtechCableModule="Light"),
                _Obj("Group", vo=_VO(("Group",)))]
        plan = {o.Name: wire for o, wire in viewport.wireframe_plan(objs)}
        self.assertEqual(plan, {"Case": True, "Board": False, "Light": False,
                                "Lib": False, "light_cable_p6": False})

    def test_free_part_role_is_not_hardware(self):
        from acadagent import viewport
        self.assertFalse(viewport.is_atech_hardware(_Obj("Bracket", AtechRole="case")))
        self.assertFalse(viewport.is_atech_hardware(_Obj("Bracket")))


if __name__ == "__main__":
    unittest.main()
