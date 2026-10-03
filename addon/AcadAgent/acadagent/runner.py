"""runner — execute agent-authored geometry code against FreeCAD's document.

THE RULE THIS FILE EXISTS TO ENFORCE
    FreeCAD's GUI is not thread-safe. A worker thread must NEVER touch a
    widget or the document. This module runs work and emits Qt signals; the
    panel connects to those signals and does all widget work on the main
    thread.

WHAT COUNTS AS A RESULT
    Geometry facts are MEASURED off the resulting shape - volume, solid
    count, validity, bbox - never taken from the parameters that produced it.
    A value that cannot be measured is returned as None with a reason, never
    a plausible substitute.

    Two FreeCAD traps this measures around:
      - a fuse that does not intersect yields TWO solids while isValid()
        still returns True. Hence solids is always reported.
      - Shape.BoundBox is a BOUND, not a measurement, and is wrong in both
        directions on curved bodies. It is reported as bbox_bound and
        labelled as such.
"""
import traceback

from PySide6 import QtCore


def measure(obj):
    """Measure a document object's shape. Returns a dict; None where unknown.

    Never asserts. Every value here comes off the solid. bbox_tight is
    optimalBoundingBox - tight to the geometry; bbox_bound is Shape.BoundBox,
    kept and labelled as the loose bound it is (PRD S14).
    """
    out = {
        "name": getattr(obj, "Name", None),
        "label": getattr(obj, "Label", None),
        "volume_mm3": None,
        "area_mm2": None,
        "solids": None,
        "valid": None,
        "bbox_bound": None,
        "bbox_tight": None,
        "reason": None,
    }
    shape = getattr(obj, "Shape", None)
    if shape is None:
        out["reason"] = "object has no Shape (not a solid-bearing feature)"
        return out
    try:
        out["valid"] = bool(shape.isValid())
        out["solids"] = len(shape.Solids)
        out["volume_mm3"] = round(shape.Volume, 3)
        out["area_mm2"] = round(shape.Area, 3)
        bb = shape.BoundBox
        out["bbox_bound"] = [round(bb.XLength, 3), round(bb.YLength, 3),
                             round(bb.ZLength, 3)]
    except Exception as exc:                      # noqa: BLE001
        out["reason"] = "measurement failed: %s" % exc
        return out
    try:
        tb = shape.optimalBoundingBox(True, False)
        out["bbox_tight"] = [round(tb.XLength, 3), round(tb.YLength, 3),
                             round(tb.ZLength, 3)]
    except Exception:                             # noqa: BLE001
        pass                    # stays None: unknown, not the loose bound
    return out


class DocWorker(QtCore.QThread):
    """Run a callable off the GUI thread and report via signals.

    IMPORTANT: the callable must not touch FreeCAD's document or any widget.
    Use this for genuinely off-thread work (network, subprocess, file IO).
    Document mutation happens on the main thread - see panel.run_on_main.
    """

    line = QtCore.Signal(str)
    done = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            result = self._fn(self._emit)
        except Exception as exc:                  # noqa: BLE001
            self.failed.emit("%s: %s" % (type(exc).__name__, exc))
            return
        if not self._cancelled:
            self.done.emit(result)

    def _emit(self, text):
        if not self._cancelled:
            self.line.emit(str(text))


def apply_code(code, doc_name=None, filename=None, env_out=None):
    """Execute agent-authored geometry code against the active document.

    MUST be called on the main thread. Returns (ok, output, measurements).

    `filename` is what tracebacks name: pass the real model.py path so the
    agent reads `File ".../model.py", line 7` rather than "<agent>" (S13).
    `env_out`, a dict, receives INTENDED_OVERLAPS if the script set it.

    Recompute is forced and validity is measured afterwards, so a build that
    produces a broken solid reports as broken rather than silently passing.
    Headless (no GUI) direct `X.ViewObject.attr = v` lines are recorded into
    env_out["view"] instead of failing on a ViewObject that does not exist.
    """
    import FreeCAD
    import io
    import contextlib

    doc = (FreeCAD.getDocument(doc_name) if doc_name
           else FreeCAD.ActiveDocument)
    if doc is None:
        doc = FreeCAD.newDocument("Untitled")

    before = {o.Name for o in doc.Objects}
    buf = io.StringIO()
    env = {"FreeCAD": FreeCAD, "App": FreeCAD, "doc": doc, "__name__": "__agent__"}
    try:
        import FreeCADGui
        env["FreeCADGui"] = FreeCADGui
        env["Gui"] = FreeCADGui
    except ImportError:
        pass
    source = code
    view = {}
    if not getattr(FreeCAD, "GuiUp", False):
        try:
            import atech_geom            # agent_kit, put on sys.path by build
            source = atech_geom.record_view(code)
            env[atech_geom.VIEW_FN] = atech_geom.view_recorder(view)
        except Exception:                         # noqa: BLE001
            source = code                # a syntax error reports below

    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(source, filename or "<agent>", "exec"), env)   # noqa: S102
        doc.recompute()
    except BaseException:                         # noqa: BLE001
        # BaseException, not Exception: a script ending in sys.exit(main())
        # raises SystemExit, which escaped the Qt slot and ended the whole
        # app (measured by review, 2026-09-24). Agent code never gets to quit
        # Studio.
        return False, buf.getvalue() + traceback.format_exc(), []
    finally:
        if env_out is not None:
            env_out["INTENDED_OVERLAPS"] = env.get("INTENDED_OVERLAPS")
            env_out["view"] = view

    created = [o for o in doc.Objects if o.Name not in before]
    targets = created or list(doc.Objects)
    return True, buf.getvalue(), [measure(o) for o in targets]
