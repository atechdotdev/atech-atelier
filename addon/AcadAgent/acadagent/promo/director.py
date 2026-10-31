"""Promo director: the style of one product's video - its title, tagline,
environment, accent colour, captions, what spins and what glows.

defaults() picks it from the product's name and parts (no tokens);
direct() asks Claude (one short, tool-less reply) and keeps every field
it got right, falling back to defaults() field by field.
"""
import json
import re
import subprocess

import stage
import timeline

_ENV_WORDS = [
    ("neon", r"arcade|game|console|music|synth|macro|keypad|midi|retro|dj|gamepad|controller"),
    ("night", r"night|alarm|moon|sleep|bedside|star|clock"),
    ("garden", r"plant|garden|weather|soil|outdoor|bird|flower|water"),
    ("kitchen", r"feeder|pet|kitchen|coffee|food|cook|dispens|scale"),
    ("workshop", r"rover|tank|car|truck|vehicle|robot car|drone|track|explorer|balanc"),
    ("blueprint", r"robot|arm|bracket|gear|mount|dock|tool|jig|hinge|sensor"),
    ("sunset", r"speaker|doorbell|photo|frame|lamp|light|metronome|music box"),
    ("desk", r"desk|fan|organi[sz]er|pad|pen|monitor|lamp|timer"),
]


def environment_for(text):
    t = (text or "").lower()
    for env, pat in _ENV_WORDS:
        if re.search(pat, t):
            return env
    return "studio"


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(max(0, min(1, x)) * 255) for x in c[:3])


def _accent(parts):
    """The most colourful body colour of the product, else None."""
    best, score = None, 0.18
    for p in parts:
        if p.get("kind") in ("board", "module", "cable"):
            continue
        c = p.get("color") or ()
        if len(c) < 3:
            continue
        s = max(c[:3]) - min(c[:3])
        if s > score and max(c[:3]) > 0.35:
            best, score = c, s
    return _hex(best) if best is not None else None


def defaults(context, parts):
    title = str(context.get("title") or "").strip() or "My design"
    title = timeline.pretty(title)
    mods = []
    for p in parts:
        if p.get("kind") == "module":
            n = p.get("name") or timeline.pretty(p.get("label"))
            if n not in mods:
                mods.append(n)
    if mods:
        tag = "Built around Atech %s" % (", ".join(mods[:3]) + (" and more" if len(mods) > 3 else ""))
    else:
        tag = "Designed in Atech Atelier"
    text = " ".join([title, str(context.get("request") or ""), str(context.get("archetype") or "")])
    env = environment_for(text)
    return {"title": title[:40], "tagline": tag[:80], "environment": env,
            "accent": _accent(parts) or _hex(stage.environment(env)["accent"]),
            "hero_az": 32, "captions": {}, "spin": None, "glow": None, "source": "defaults"}


# ---------------------------------------------------------------- Claude
PROMPT = """You are the director of a short promo video for a product someone just
designed in a CAD app. The video: 2 s hero shot of the finished product, then
it assembles from nothing - electronics first, then every printed part, then
the screws - then it powers on (lit parts glow, rotors and wheels spin) on a
turntable, and an end card shows the title and tagline.

Choose its style. Answer with ONE JSON object and nothing else:
{{
  "title": "<product name, max 28 chars, catchy but honest>",
  "tagline": "<one line, max 70 chars, what it does / why it is fun>",
  "environment": "<one of: {envs}>",
  "accent": "<#rrggbb: an accent colour that suits the product's own colours>",
  "hero_az": <camera side in degrees: 20..45 front-left, -45..-20 front-right; the side that shows its face>,
  "captions": {{"<part label>": "<max 40 chars: what this part is or does>", ...}},
  "spin": [{{"part": "<label>", "axis": "x|y|z", "speed": <0.3..2>}}],
  "glow": [{{"part": "<label>", "color": "#rrggbb"}}]
}}
Rules: use part labels exactly as listed. Captions for up to 12 parts that
matter (skip screws and feet). spin: only parts that really rotate in use
(fan rotors, wheels, knobs on a turntable...), axis = the world axis it turns
about; [] if none. glow: only see-through lenses, diffusers, light windows or
screens that light up; [] if none.

Environments:
{envlist}

The product: {title}
{request}
Parts (label | kind | colour | size mm | notes):
{parts}
"""


def _part_lines(parts, limit=60):
    out = []
    for p in parts[:limit]:
        bits = [str(p.get("label")), p.get("kind") or "body", _hex(p.get("color") or (0.8, 0.8, 0.8))]
        sz = p.get("size")
        if sz:
            bits.append("x".join("%.0f" % v for v in sz))
        notes = []
        if p.get("name"):
            notes.append(p["name"])
        if p.get("ports"):
            notes.append("port " + "+".join(str(x) for x in p["ports"]))
        if float(p.get("transparency") or 0) > 0:
            notes.append("see-through %d%%" % int(p.get("transparency")))
        bits.append(", ".join(notes))
        out.append(" | ".join(bits))
    if len(parts) > limit:
        out.append("... and %d more" % (len(parts) - limit))
    return "\n".join(out)


def prompt(context, parts):
    req = str(context.get("request") or "").strip()
    return PROMPT.format(
        envs=", ".join(stage.ENVIRONMENTS),
        envlist="\n".join("  %s: %s" % kv for kv in stage.ENVIRONMENTS.items()),
        title=context.get("title") or "untitled",
        request=("What they asked for: " + req[:600]) if req else "",
        parts=_part_lines(parts))


def parse(text):
    """The first JSON object in `text`, or None."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def merge(base, got, parts):
    """`base` with every valid field of Claude's answer `got`."""
    out = dict(base)
    if not isinstance(got, dict):
        return out
    labels = {str(p.get("label")).lower() for p in parts}
    if isinstance(got.get("title"), str) and got["title"].strip():
        out["title"] = got["title"].strip()[:40]
    if isinstance(got.get("tagline"), str) and got["tagline"].strip():
        out["tagline"] = got["tagline"].strip()[:80]
    if got.get("environment") in stage.ENVIRONMENTS:
        out["environment"] = got["environment"]
    if timeline.hexrgb(got.get("accent")):
        out["accent"] = got["accent"]
    try:
        az = float(got.get("hero_az"))
        if -60 <= az <= 60:
            out["hero_az"] = az
    except (TypeError, ValueError):
        pass
    caps = got.get("captions")
    if isinstance(caps, dict):
        out["captions"] = {str(k): str(v)[:44] for k, v in caps.items()
                           if str(k).lower() in labels and isinstance(v, str) and v.strip()}
    for key in ("spin", "glow"):
        v = got.get(key)
        if isinstance(v, list):
            out[key] = [x for x in v if isinstance(x, dict)
                        and str(x.get("part", "")).lower() in labels][:8]
    out["source"] = "claude"
    return out


def direct(context, parts, log=lambda m: None, timeout=150):
    """The spec for this video: Claude's (context["director_argv"], a
    claude -p argv without the prompt) merged over defaults()."""
    base = defaults(context, parts)
    argv = context.get("director_argv")
    if not argv:
        return base
    try:
        p = subprocess.run(list(argv), input=prompt(context, parts), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        log("director: %r" % (exc,))
        return base
    out = p.stdout or ""
    text = out
    try:
        j = json.loads(out)
        if isinstance(j, dict):
            text = j.get("result") or ""
            if j.get("is_error"):
                log("director: claude error: %s" % str(text)[:200])
                return base
    except ValueError:
        pass
    got = parse(text)
    if got is None:
        log("director: no JSON in the reply (%s)" % (p.stderr or out)[-300:])
        return base
    return merge(base, got, parts)
