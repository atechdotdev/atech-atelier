"""capture — put the 3D viewport in front of the agent.

This is the FreeCAD half of the screenshot round trip the Claude desktop app
does today through freecad-mcp's `get_view`. Reference implementation:
    tools/freecad-mcp/addon/FreeCADMCP/rpc_server/view_manager.py:94
    tools/freecad-mcp/addon/FreeCADMCP/rpc_server/rpc_server.py:354

WHAT IS DIFFERENT HERE, AND WHY IT IS SIMPLER
    freecad-mcp is an RPC server: its calls arrive on a socket thread, so it
    must hop to the GUI thread via dispatch_to_gui() before touching a view.
    We are already IN the process, called from the panel, on the GUI thread.
    So no dispatch is needed - but "already on the GUI thread" is an
    assumption, and an assumption that is wrong produces an intermittent
    crash deep in Coin3D rather than an error. So we ASSERT it: capture()
    raises CaptureError if called off the GUI thread rather than doing it
    anyway. See _require_gui_thread().

WHAT CAN GO WRONG, AND WHAT WE RETURN WHEN IT DOES
    There is no view at all (no document open)          -> CaptureError
    The view is a TechDraw page or a Spreadsheet        -> CaptureError
        Those view classes have no saveImage(). The reference checks
        hasattr(view, "saveImage") for exactly this reason.
    saveImage() succeeds but writes a 0-byte / unreadable file
        -> CaptureError. A path is returned ONLY when a file exists at it
        with a plausible PNG header. Returning a path to a broken file is
        the P1 failure: absent data wearing a confident shape. panel.Shot
        would render "Capture could not be read." and the agent would be
        handed a corrupt attachment.

    Every failure raises with a NAMED cause. None of them returns a path.

STALE FRAMES
    saveImage() can grab the previous frame if the scene changed in the same
    event-loop turn. The reference hit this on Linux (#51/#53) and pumps the
    event loop before saving. We do the same via _flush().
"""
import os
import tempfile
import time

CaptureError = type("CaptureError", (RuntimeError,), {})

# What the USER is told for each kind of failure (R26). The technical cause
# stays on the exception and goes to the Report view; the chat never shows
# a method name like saveImage().
_USER_NO_DOC = "Open a document first: there is no 3D view to capture."
_USER_NOT_3D = "Switch to the 3D view, then add the view again."
_USER_FAILED = ("The 3D view could not be saved as a picture. The details "
                "are in the Report view.")


def _err(technical, user=_USER_FAILED):
    exc = CaptureError(technical)
    exc.user_text = user
    return exc


def user_message(exc):
    """The plain sentence for a CaptureError (or anything else)."""
    return getattr(exc, "user_text", None) or _USER_FAILED

#: PNG magic. A file that does not start with this is not a PNG, whatever
#: its extension says.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: Orientations FreeCAD's view understands, as used by freecad-mcp.
VIEWS = ("Isometric", "Front", "Top", "Right", "Rear", "Bottom", "Left",
         "Dimetric", "Trimetric")

#: Not a FreeCAD standard view: the side an Atech board's modules face
#: (R145). "Ask about this view" forced Isometric, which looks from -Y at a
#: board lying in XZ whose modules face +Y: the agent was shown the back of
#: the board. The direction is viewport.module_face_direction's, the one the
#: chat's first build turns to (R82); a board with nothing seated on it
#: keeps the user's camera.
MODULE_FACE = "Module face"


def module_face(doc=None):
    """The camera-position direction toward an Atech board's modules in
    `doc` (default: the active document), or None when there is no board
    with a seated module (or it cannot be measured). Never raises."""
    try:
        if doc is None:
            import FreeCAD
            doc = FreeCAD.ActiveDocument
        if doc is None:
            return None
        from . import viewport
        return viewport.module_face_direction(doc)
    except Exception as exc:                              # noqa: BLE001
        _log("module face: %r" % (exc,))
        return None


_SESSION_DIR = None


def session_dir():
    """A private (0700) temp folder for captures that have no chat
    workspace to go to, created once per Studio session and removed when
    Studio exits (R35: captures used to pile up in /tmp forever)."""
    global _SESSION_DIR
    if _SESSION_DIR and os.path.isdir(_SESSION_DIR):
        return _SESSION_DIR
    _SESSION_DIR = tempfile.mkdtemp(prefix="atech-views-")
    import atexit
    atexit.register(cleanup_session_dir)
    try:
        # FreeCAD's GUI does not always run atexit handlers; Qt's quit does.
        from PySide6 import QtCore
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(cleanup_session_dir)
    except Exception:                                     # noqa: BLE001
        pass
    return _SESSION_DIR


def cleanup_session_dir():
    """Remove the session's capture folder. Safe to call twice."""
    global _SESSION_DIR
    d, _SESSION_DIR = _SESSION_DIR, None
    if d:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintMessage("AcadAgent capture: %s\n" % msg)
    except Exception:                                     # noqa: BLE001
        pass


def _require_gui_thread():
    """Refuse to touch a view from a worker thread.

    Qt/Coin3D will not raise here - it will corrupt or crash, sometimes
    much later. A clear refusal now is worth more than a capture that
    usually works.
    """
    try:
        from PySide6 import QtCore
    except ImportError:                                   # no Qt -> headless
        return
    app = QtCore.QCoreApplication.instance()
    if app is None:
        return
    if QtCore.QThread.currentThread() is not app.thread():
        raise CaptureError(
            "capture() must run on the GUI thread; it was called from a "
            "worker thread. Marshal to the GUI thread first "
            "(QMetaObject.invokeMethod / a queued signal).")


def _flush():
    """Let the viewport finish redrawing before we grab the frame."""
    try:
        from PySide6 import QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents()
    except Exception:                                     # noqa: BLE001
        pass


def _active_view():
    """The active 3D view, or a NAMED reason there is not one."""
    try:
        import FreeCADGui
    except ImportError:
        raise _err("FreeCADGui is not available (running without a GUI).")

    doc = getattr(FreeCADGui, "ActiveDocument", None)
    if doc is None:
        raise _err("No document is open, so there is no viewport to "
                   "capture.", _USER_NO_DOC)

    view = getattr(doc, "ActiveView", None)
    if view is None:
        raise _err("The active document has no active view.", _USER_NOT_3D)

    # TechDraw pages and Spreadsheets are views with no saveImage(). This is
    # the reference implementation's own guard (rpc_server.py:374).
    if not hasattr(view, "saveImage"):
        raise _err(
            "The active view (%s) does not support screenshots. Switch to a "
            "3D view." % type(view).__name__, _USER_NOT_3D)
    return view


class _still_camera(object):
    """Turn the view's camera animation off for the capture, and stop one
    already running; restored afterwards (R138).

    A standard-view turn (viewIsometric) is ANIMATED when FreeCAD's
    navigation animations are on (the default). The animation keeps moving
    the camera on later event-loop turns - including the processEvents()
    in _flush() - so it overwrote the fit, and the offscreen render used
    clip planes the on-screen view never redrew for: the model fell
    outside them and the capture was an empty background."""

    def __init__(self, view):
        self.view = view
        self.was = None

    def __enter__(self):
        v = self.view
        try:
            self.was = bool(v.isAnimationEnabled())
            v.setAnimationEnabled(False)
        except Exception as exc:                          # noqa: BLE001
            self.was = None
            _log("cannot turn the view animation off: %s" % exc)
        try:
            v.stopAnimating()
        except Exception:                                 # noqa: BLE001
            pass
        return self

    def __exit__(self, *exc):
        if self.was is not None:
            try:
                self.view.setAnimationEnabled(self.was)
            except Exception as err:                      # noqa: BLE001
                _log("cannot restore the view animation: %s" % err)
        return False


#: R176: a user camera whose look direction is within this angle's cosine
#: of the module-face direction already shows the modules: the capture keeps
#: it. The Modules page's board camera (projects.board_view_rotation) is
#: 43 deg from the module-face direction (cos 0.734), the isometric corner
#: looks at the back (cos < 0).
FACING_COS = 0.5


def _unit(v):
    n = sum(c * c for c in v) ** 0.5
    return tuple(c / n for c in v) if n > 1e-12 else None


def user_axes(view):
    """(look, up) unit vectors of the view's camera in world coordinates,
    or None when the view cannot report its orientation."""
    try:
        import FreeCAD
        r = view.getCameraOrientation()
        lk = r.multVec(FreeCAD.Vector(0, 0, -1))
        up = r.multVec(FreeCAD.Vector(0, 1, 0))
        lk, up = _unit((lk.x, lk.y, lk.z)), _unit((up.x, up.y, up.z))
    except Exception as exc:                              # noqa: BLE001
        _log("camera orientation unreadable: %r" % (exc,))
        return None
    if lk is None or up is None:
        return None
    return lk, up


def face_turn(d, axes):
    """How to show the module face for camera-position direction `d`, given
    the user's camera `axes` ((look, up) or None). Pure math. Returns
      ("keep", None)   the user already looks at the modules: no turn;
      ("turn", up)     look along -d with world `up` = (0, 0, +-1), the
                       sign of the user's screen-up along world Z.

    R176, MEASURED headless on a board + Light (port 3): the old capture
    always turned to -d with world Z up, screen-up (-0.20, -0.34, 0.92),
    while the Modules page's board camera (its default "port7" roll,
    projects.BOARD_CAMERA_UPS) has screen-up (-0.16, 0.53, -0.83): dot
    -0.91, so the thumbnail was the live view turned ~180 deg (GUI r7_08).
    The thumbnail now shows what the user sees: the same camera when it
    already faces the modules, else the module face held the user's way up
    (world Z up for chat builds and the isometric corner, world Z down for
    the Modules page's board camera)."""
    dn = _unit(d)
    if dn is None or axes is None:
        return "turn", (0.0, 0.0, 1.0)
    look, up = axes
    if -sum(a * b for a, b in zip(look, dn)) >= FACING_COS:
        return "keep", None
    return "turn", (0.0, 0.0, -1.0 if up[2] < 0 else 1.0)


def _face_modules(view, d):
    """Turn `view` to the module face `d` the way the user holds the
    camera (R176): kept when it already shows the modules, else turned
    with world Z up (viewport.look_from, as the chat's first build) or,
    when the user's screen-up points down world Z, with world Z down."""
    from . import viewport
    how, up = face_turn(d, user_axes(view))
    if how == "keep":
        _log("the camera already shows the module face: kept")
        return
    if up[2] < 0:
        try:
            q = viewport.look_quaternion((-d[0], -d[1], -d[2]), up=up)
            view.setCameraOrientation(q)
            return
        except Exception as exc:                          # noqa: BLE001
            _log("module face held Z-down failed: %r" % (exc,))
    if not viewport.look_from(*d, v=view):
        _log("could not turn to the module face: keeping the camera")


def _orient(view, view_name):
    """Point the camera. An unknown name is reported, never silently ignored."""
    if not view_name:
        return
    if view_name == MODULE_FACE:
        d = module_face()
        if d is None:
            _log("no module face to turn to: keeping the current camera")
            return
        _face_modules(view, d)
        return
    if view_name not in VIEWS:
        raise CaptureError("Unknown view orientation %r. Known: %s"
                           % (view_name, ", ".join(VIEWS)))
    fn = getattr(view, "view%s" % view_name, None)
    if fn is None:
        raise CaptureError("This view cannot be oriented to %r." % view_name)
    fn()


class _kept_camera(object):
    """Put the user's camera back after the capture (R159).

    capture() turns the view (Isometric / the module face) and fitAll()s it
    for the picture. Left like that, the live view stayed turned and was
    fitted by FreeCAD's plain ViewFit, which centres the model in the WHOLE
    view: its bottom then sat under the floating view bar (GUI r6_09,
    r6_16). The picture needs the turn and the fit; the user's screen does
    not, so the camera the user had is restored once the frame is saved.

    Restored with the view's own getCamera()/setCamera() (the camera node
    as Inventor text: type, position, orientation, height/focal distance,
    clip planes). A view that cannot report its camera is left as the
    capture put it, and that is logged, never silently assumed."""

    def __init__(self, view):
        self.view = view
        self.saved = None

    def __enter__(self):
        try:
            self.saved = self.view.getCamera()
        except Exception as exc:                          # noqa: BLE001
            self.saved = None
            _log("cannot read the camera, it will stay turned: %s" % exc)
        return self

    def __exit__(self, *exc):
        if self.saved:
            try:
                self.view.setCamera(self.saved)
            except Exception as err:                      # noqa: BLE001
                _log("cannot restore the camera: %s" % err)
        return False


def _verify_png(path):
    """A path is only worth returning if a real PNG is actually at it."""
    if not os.path.exists(path):
        raise CaptureError("saveImage() reported no error but wrote no file.")
    size = os.path.getsize(path)
    if size == 0:
        raise CaptureError("saveImage() wrote a 0-byte file.")
    with open(path, "rb") as fh:
        head = fh.read(8)
    if head != _PNG_MAGIC:
        raise CaptureError(
            "saveImage() wrote %d bytes that are not a PNG (header %r)."
            % (size, head))
    return size


def capture(path=None, width=1200, height=900, view_name="Isometric",
            fit=True, background="Current", restore=True):
    """Save the active 3D viewport to a PNG and return its path.

    Args:
        path:       where to write. None -> a file in session_dir(), which
                    is removed when Studio exits.
        width/height: pixels. Independent of the on-screen widget size.
        view_name:  an entry of VIEWS, or None to keep the current camera.
        fit:        fitAll() before capturing, so the model is in frame.
        background: "Current" keeps the themed viewport background, which is
                    what the user is actually looking at. The alternatives
                    ("White", "Black", "Transparent") re-render on a
                    different ground and no longer match the screen.
        restore:    put the user's camera back after the capture (R159), so
                    the turn and fit made for the picture never move the
                    live view.

    Returns:
        str: an absolute path to a verified, non-empty PNG.

    Raises:
        CaptureError: with a named cause. Never returns a path on failure.
    """
    _require_gui_thread()
    view = _active_view()

    if path is None:
        fd, path = tempfile.mkstemp(prefix="view-", suffix=".png",
                                    dir=session_dir())
        os.close(fd)
    path = os.path.abspath(path)

    # R138: no camera animation while we point, fit and save (see
    # _still_camera). MEASURED in an offscreen Studio: viewIsometric() with
    # navigation animations on, then fitAll(), then one event-loop turn -
    # the animation's next frame moved the camera to focal 250 mm with the
    # fit's clip planes (far 131 mm), and saveImage() wrote a blank
    # 1200x900 background (0 of 120 000 sampled pixels off the gradient)
    # of a board + Light document the screen showed fine.
    # R159: the camera is restored INSIDE _still_camera, so putting it back
    # is not animated either.
    with _still_camera(view), \
            (_kept_camera(view) if restore else _nothing()):
        _orient(view, view_name)

        if fit:
            try:
                view.fitAll()
            except Exception as exc:                      # noqa: BLE001
                _log("fitAll failed, capturing unfitted: %s" % exc)

        # Redraw before grabbing, or we may save the PREVIOUS frame.
        _flush()

        try:
            view.saveImage(path, int(width), int(height), background)
        except Exception as exc:                          # noqa: BLE001
            raise CaptureError("saveImage() failed: %s: %s"
                               % (type(exc).__name__, exc))

    size = _verify_png(path)
    _log("wrote %s (%d bytes, %dx%d, %s)"
         % (path, size, width, height, view_name or "current camera"))
    return path


class _nothing(object):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


#: capture_to_panel's default: the view vision.views_for() picks for the
#: active document (R158) - the module face of an Atech board, Isometric
#: otherwise.
AUTO = "auto"


def default_view(doc=None):
    """The view "Add view" captures of `doc` (default: the active
    document): vision.views_for's first, so the composer and "Ask about
    this view" look from the same side (R145, R158). Isometric when that
    cannot be told."""
    try:
        from . import vision
        views = vision.views_for(doc)
        return views[0] if views else "Isometric"
    except Exception as exc:                              # noqa: BLE001
        _log("default view: %r" % (exc,))
        return "Isometric"


def default_caption(view_name="Isometric", doc_name=None):
    """The line under the image in the panel: what, of what, when."""
    if doc_name is None:
        try:
            import FreeCAD
            doc = FreeCAD.ActiveDocument
            doc_name = doc.Label if doc is not None else "no document"
        except Exception:                                 # noqa: BLE001
            doc_name = "unknown"
    stamp = time.strftime("%H:%M:%S")
    return "%s - %s view - %s" % (doc_name, view_name or "current", stamp)


def capture_to_panel(panel, width=1200, height=900, view_name=AUTO,
                     fit=True, path=None):
    """Capture the viewport and show it inline in the chat.

    view_name AUTO (the default) = default_view(): R158, the composer's
    "Add view" on an Atech board captured Isometric, the back of the board.

    panel.add_shot(path, caption) is panel.py's own API; this is its first
    caller. On failure a PLAIN reason is shown in the chat (the technical
    cause goes to the Report view) rather than a broken image placeholder.

    path: where to write. None asks the panel (panel.capture_path(), the
    chat's own workspace, so the agent may read it and it is cleared with
    the chat), else session_dir().

    Returns:
        str | None: the path on success, None on a handled failure.
    """
    if path is None:
        where = getattr(panel, "capture_path", None)
        if callable(where):
            try:
                path = where()
            except Exception as exc:                      # noqa: BLE001
                _log("capture_path failed, using a temp file: %s" % exc)
                path = None
    if view_name == AUTO:
        view_name = default_view()
    try:
        path = capture(path=path, width=width, height=height,
                       view_name=view_name, fit=fit)
    except CaptureError as exc:
        _log("capture failed: %s" % exc)
        add_note = getattr(panel, "add_note", None) or getattr(
            panel, "add_error", None)
        if callable(add_note):
            add_note(user_message(exc))
        return None

    panel.add_shot(path, default_caption(view_name))
    return path
