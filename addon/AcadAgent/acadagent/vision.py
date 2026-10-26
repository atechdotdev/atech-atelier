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


#: R250: the budget of one "Ask about this view" question when the user set
#: none. A look at a picture is a short read-only answer, not a design turn:
#: quality mode's design defaults (claude_cli.QUALITY_BUDGET_USD and
#: QUALITY_EFFORT) never apply here.
VIEW_BUDGET_USD = 3.00


def view_settings(cfg=None):
    """R250: agent_argv() keyword arguments for a view question - the
    user's own model, effort and budget when they set them (Agent Settings),
    else the CLI's own effort (none forced) and VIEW_BUDGET_USD, whatever
    the design mode. A budget field left empty ("") or 0 means no limit, as
    for the chat (claude_cli.agent_settings)."""
    if cfg is None:
        try:
            from . import settings
            cfg = settings.load()
        except Exception:                                 # noqa: BLE001
            cfg = {}
    model = cfg.get("agent_model")
    model = model.strip() if isinstance(model, str) and model.strip() else None
    effort = cfg.get("agent_effort")
    effort = effort.strip() if isinstance(effort, str) and effort.strip() else None
    raw = cfg.get("agent_budget_usd")
    if raw is None:
        budget = VIEW_BUDGET_USD
    elif raw == "":
        budget = None                     # an empty field: no limit
    else:
        try:
            budget = float(raw)
        except (TypeError, ValueError):
            budget = VIEW_BUDGET_USD
    return {"model": model, "effort": effort, "budget": budget}


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
    agent = view_agent(cwd)                               # R250, R500
    run = claude_cli.ClaudeRun(prompt, cwd=cwd, session_id=session_id,
                               images=paths, permission_mode=permission_mode,
                               parent=parent, agent=agent)
    return run


DEFAULT_QUESTION = ("Describe this model: what is it, what are its main "
                    "parts, and is anything visibly wrong or overlapping?")


def ask_in_chat(question=None, views=None, panel=None):
    """"Ask about this view" IN THE CHAT (R36 target, R500).

    R500 (PRD "Agent integration" 2): the view is captured EXACTLY as the
    user framed it - the current camera, no turn to Isometric or the module
    face, no fit - into the chat workspace as an inline shot, and the
    composer opens with it attached (panel.open_view_question): whatever
    the user had typed stays, nothing is sent until they send it. That
    reply runs read-only (view_settings: the $3 view budget, VIEW_TOOLS,
    plan mode), so it never writes to the workspace.

    `question` given (an old caller, terminal_dock.ask_about_view): the
    question is sent at once, read-only, with the same capture. `views`
    given: those named views are captured (fitted) instead of the camera.

    Returns True when the composer is open with the view (or the turn
    started); False with the reason already shown in the chat otherwise."""
    p = panel or _chat_panel()
    if p is None:
        raise RuntimeError("the chat is not open")
    paths = []
    if views is None:
        path = capture.capture_to_panel(p, view_name=None, fit=False)
        if path:
            paths.append(path)
    else:
        for name in views:
            path = capture.capture_to_panel(p, view_name=name)
            if path:
                paths.append(path)
    if not paths:
        return False            # capture_to_panel put the reason in the chat
    opener = getattr(p, "open_view_question", None)
    if question:
        ask = getattr(p, "ask_view", None)
        if callable(ask):
            return bool(ask(question, paths))
        return bool(p.ask(question))
    if callable(opener):
        return bool(opener(paths))
    return bool(p.ask(DEFAULT_QUESTION))


def view_prompt(question, paths, brief=""):
    """R500: the prompt of a view question asked in the chat: what the
    images are (_compose) and the document brief after it."""
    text = _compose(question, list(paths or ()), [])
    return "%s\n\n---\n%s" % (text, brief) if brief else text


def view_agent(ws, cfg=None):
    """R500: agent_argv() keyword arguments of a view question: the user's
    own model / effort / budget or the $3 view budget (view_settings), no
    Bash allowlist and only the read tools (claude_cli.VIEW_TOOLS)."""
    return dict(view_settings(cfg), ws=ws, allowed=(),
                tools=claude_cli.VIEW_TOOLS)


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
