"""style.py's token tables must equal brand/tokens.py, the brand's source.

The addon ships alone inside the AppImage and cannot import brand/, so it
carries a copy. This test is what keeps the copy honest. Read with ast so it
runs without PySide6 or FreeCAD.
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
STYLE = os.path.join(HERE, "..", "acadagent", "style.py")


def _dicts(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = ast.literal_eval(node.value)
    return out


class TokensMatchBrand(unittest.TestCase):
    def test_modes(self):
        sys.path.insert(0, os.path.join(REPO, "brand"))
        import tokens
        mine = _dicts(STYLE)
        for mode, brand in (("light", tokens.LIGHT), ("dark", tokens.DARK)):
            ours = mine[mode.upper()]
            want = dict(brand)
            want.update(tokens.STATUS[mode])
            for key, value in want.items():
                self.assertEqual(ours.get(key), value,
                                 "%s.%s drifted from brand/tokens.py" % (mode, key))


if __name__ == "__main__":
    unittest.main()
