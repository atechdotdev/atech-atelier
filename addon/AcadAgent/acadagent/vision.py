"""vision — the round trip between the 3D renderer and the agent.

THE ONE THING THIS FILE GUARANTEES
    What the agent looks at is a PNG of the ACTUAL viewport at the moment of
    asking — never a cached frame, never a stand-in, never a description of
    geometry generated from parameters. capture.py already refuses to return
    a path unless a readable PNG exists there; this module refuses to call
    the agent unless capture.py returned one.

WHY THAT MATTERS HERE
    The whole product claim is that the number on screen traces to a real
    solid. An agent reasoning about a stale or substituted image would
    produce confident statements about geometry nobody rendered — failure
    pattern P1 wearing a picture instead of a number.

MEASURED 2026-09-24
    claude 2.1.232 reads an image when the prompt names its path: handed a
    viewport PNG it called its own Read tool on the file and identified
    ATL-CRANE-003 unprompted. So no upload protocol, no base64, no MCP
    server is needed for the image half — only a real file on disk.

MULTI-VIEW
    One isometric frame hides self-occluded geometry. `capture_views()`
    takes several named views so the agent can see round the back, which is
    the visual equivalent of measuring rather than asserting.
"""
import os
import time

from . import capture, claude_cli


# Names must be ones capture.VIEWS accepts — it RAISES on an unknown name
# rather than silently giving the same view twice. Validated at import against
# capture.VIEWS so the two lists cannot drift apart.
STANDARD_VIEWS = ("Isometric", "Front", "Right", "Top")
_unknown = [v for v in STANDARD_VIEWS if v not in capture.VIEWS]
if _unknown:
    raise ImportError("vision.STANDARD_VIEWS names views capture.py does not "
                      "know: %s (known: %s)"
                      % (", ".join(_unknown), ", ".join(capture.VIEWS)))


def _chat_panel():
    """The chat panel, if the shell has one (never creates it)."""
    try:
        from . import shell
        return shell.chat_panel()
    except Exception:                                     # noqa: BLE001
        return None


def chat_workspace():
    """The active document's chat workspace, or None (R36): the agent works
    there and captures land there, instead of $HOME and /tmp."""
    p = _chat_panel()
    if p is None:
        return None
    try:
        return os.path.dirname(p.capture_path())
    except Exception:                                     # noqa: BLE001
        return None


def is_board_document(doc):
    """True when `doc` holds an Atech board (AtechRole == "board")."""
    try:
        return any(getattr(o, "AtechRole", None) == "board"
                   for o in (getattr(doc, "Objects", None) or ()))
    except Exception:                                     # noqa: BLE001
        return False


def views_for(doc=None):
    """The view(s) "Ask about this view" captures for `doc` (default: the
    active document). R145: a board document is looked at from its modules'
    side (capture.MODULE_FACE: the current camera when no module is seated),
    never from the isometric corner that shows the back of the board. Other
    documents keep the isometric view."""
    if doc is None:
        try:
            import FreeCAD
            doc = FreeCAD.ActiveDocument
        except Exception:                                 # noqa: BLE001
            doc = None
    if doc is not None and is_board_document(doc):
        return (capture.MODULE_FACE,)
    return ("Isometric",)


def capture_views(views=STANDARD_VIEWS, width=1200, height=900, fit=True,
                  dest=None):
    """Capture several viewpoints. Returns (paths, failures).

    dest: the folder to write into; None = the chat workspace, else the
    session capture folder that is removed when Studio exits (R35).

    A view that cannot be captured contributes a NAMED failure and no path.
    Partial success is reported as partial, never rounded up to success.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tmp = dest or chat_workspace() or capture.session_dir()
    paths, failures = [], []
    for name in views:
        target = os.path.join(tmp, "%s_%s.png"
                              % (stamp, name.lower().replace(" ", "-")))
        try:
            p = capture.capture(path=target, width=width, height=height,
                                view_name=name, fit=fit)
        except Exception as exc:
            failures.append("%s: %s" % (name, exc))
            continue
        if p and os.path.isfile(p):
            paths.append(p)
        else:
            failures.append("%s: capture returned no readable file" % name)
    return paths, failures


def ask_about_view(question, views=None, cwd=None, session_id=None,
                   permission_mode="plan", width=1200, height=900,
                   parent=None):
    """Capture the viewport and ask the agent about what it shows.

    Returns a started ClaudeRun the caller connects signals to, or raises
    RuntimeError with a named cause. It never silently asks without an image:
    if nothing could be captured, the caller is told instead.

    permission_mode defaults to "plan" — looking at geometry is a read-only
    act, and this path must not become a way to write unreviewed changes.

    It runs in the chat workspace when there is a chat (R36), whatever
    `cwd` says; `cwd` is only the fallback. The launch is the same isolated
    one as the chat's (claude_cli.agent_argv, R78) with no Bash allowlist.
    """
    if not claude_cli.available():
        raise RuntimeError("the `claude` CLI was not found on this system")

    ws = chat_workspace()
    if views is None:
        views = views_for()                               # R145
    paths, failures = capture_views(views, width=width, height=height,
                                    dest=ws)
    if not paths:
        raise RuntimeError("could not capture the viewport — %s"
                           % ("; ".join(failures) or "no reason reported"))

    cwd = ws or cwd or os.path.dirname(paths[0])
    prompt = _compose(question, paths, failures)
    agent = dict(claude_cli.agent_settings(), ws=cwd, allowed=())
    run = claude_cli.ClaudeRun(prompt, cwd=cwd, session_id=session_id,
                               images=paths, permission_mode=permission_mode,
                               parent=parent, agent=agent)
    return run


DEFAULT_QUESTION = ("Describe this model: what is it, what are its main "
                    "parts, and is anything visibly wrong or overlapping?")


def ask_in_chat(question=None, views=None, panel=None):
    """Ask about the view IN THE CHAT (R36 target): capture the view into
    the chat workspace as an inline shot (queued for the turn, R25) and
    send the question as a normal chat turn. Returns True when the turn
    started; False with the reason already shown in the chat otherwise.

    views None = views_for(the active document) (R145: the module face of
    an Atech board). The answer is an ordinary chat reply, so it renders
    Markdown like one (panel.Bubble, R153).

    For the "Ask about this view" button (terminal_dock / shell are
    WS-SHELL's; switching the button to this is their follow-up)."""
    p = panel or _chat_panel()
    if p is None:
        raise RuntimeError("the chat is not open")
    if views is None:
        views = views_for()
    shots = 0
    for name in views:
        path = capture.capture_to_panel(p, view_name=name)
        shots += 1 if path else 0
    if not shots:
        return False            # capture_to_panel put the reason in the chat
    return bool(p.ask(question or DEFAULT_QUESTION))


def _compose(question, paths, failures):
    """Build the prompt. States what the images ARE and what is missing."""
    lines = [
        question,
        "",
        "The attached image(s) are a live capture of the Atech Atelier 3D "
        "viewport, rendered from the real B-rep solids in the open document.",
    ]
    if len(paths) > 1:
        lines.append("They are %d standard views of the same model: %s."
                     % (len(paths),
                        ", ".join(os.path.basename(p).split("_")[-1]
                                  .replace(".png", "") for p in paths)))
    if failures:
        # A view that failed is stated, so the agent does not assume it saw
        # the whole model.
        lines.append("Note: %d view(s) could not be captured (%s), so parts "
                     "of the model may not be visible."
                     % (len(failures), "; ".join(failures)))
    lines.append("")
    lines.append("Describe only what is visible. If a dimension or a "
                 "tolerance cannot be read from the image, say so rather "
                 "than estimating it — numbers come from measuring the "
                 "solid, not from a picture.")
    return "\n".join(lines)
