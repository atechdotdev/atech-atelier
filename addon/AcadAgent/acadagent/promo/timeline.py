"""Promo timeline: what every frame of the assembly video shows.

  hero      ~2 s   the finished product, a fast camera sweep, the title
  scatter   ~1 s   every part flies apart, off the stage
  assembly         from nothing, in build order:
                     1 Electronics - the Atech board drops in, each module
                       slides into its port along its real insertion axis,
                       each cable grows along its run
                     2 Body - each printed part flies home, groups of the
                       same part one after another
                     3 Fasteners - screws spin in along their own axis
  settle   ~0.7 s  a flash and confetti: it is together
  finale   ~4.5 s  power on (lights glow, rotors spin up), a turntable
                   orbit, the end card

Plan(scene, spec, context).state(f) is pure and deterministic, so every
worker process computes the same frame f on its own.
"""
import math
import re

import numpy as np

import render

FPS = 24
FASTENER = re.compile(r"(screw|bolt|nut|insert|rivet|washer)", re.I)
FOOT = re.compile(r"(rubber|foot|feet|bumper)", re.I)
SPINNER = re.compile(r"(rotor|fan|blade|propell|impeller|wheel|tyre|tire|turntable|spinner|reel|"
                     r"platter|rotat)", re.I)
GLOWER = re.compile(r"(lens|glow|diffuser|halo|globe|shade|lamp|light|led|window|moon|ring_light)",
                    re.I)
GROUP = re.compile(r"[_\s-]*\d+$")


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x, p=3):
    return 1 - (1 - clamp(x)) ** p


def ease_in(x, p=3):
    return clamp(x) ** p


def ease_in_out(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_back(x, k=1.5):
    x = clamp(x) - 1
    return 1 + (k + 1) * x ** 3 + k * x ** 2


def ease_bounce(x):
    x = clamp(x)
    n, d = 7.5625, 2.75
    if x < 1 / d:
        return n * x * x
    if x < 2 / d:
        x -= 1.5 / d
        return n * x * x + 0.75
    if x < 2.5 / d:
        x -= 2.25 / d
        return n * x * x + 0.9375
    x -= 2.625 / d
    return n * x * x + 0.984375


def lerp(a, b, x):
    return a + (b - a) * x


# ---------------------------------------------------------------- names
def pretty(label):
    s = re.sub(r"[_]+", " ", str(label or "")).strip()
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return (s[:1].upper() + s[1:]) if s else "Part"


def group_key(label):
    return GROUP.sub("", str(label or "")).lower()


def hexrgb(text, default=None):
    try:
        t = str(text).strip().lstrip("#")
        if len(t) == 3:
            t = "".join(c * 2 for c in t)
        if len(t) != 6:
            return default
        return tuple(int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- steps
class Step(object):
    def __init__(self, kind, parts, dur, title, sub="", chapter=None):
        self.kind, self.parts, self.dur = kind, list(parts), float(dur)
        self.title, self.sub, self.chapter = title, sub, chapter
        self.t0 = 0.0
        self.stagger = 0.0


def _pca_axis(T):
    P = T.reshape(-1, 3)
    if len(P) < 3:
        return np.array([0.0, 0.0, 1.0])
    Q = P - P.mean(0)
    _u, _s, vt = np.linalg.svd(Q[:: max(1, len(Q) // 4000)], full_matrices=False)
    return vt[0] / max(np.linalg.norm(vt[0]), 1e-9)


def _thin_axis(lo, hi):
    ext = np.asarray(hi) - np.asarray(lo)
    a = np.zeros(3)
    a[int(np.argmin(ext))] = 1.0
    return a


class Plan(object):
    """The whole video for one scene and one director's spec."""

    def __init__(self, scene, spec, context=None, fps=FPS):
        self.scene, self.spec, self.fps = scene, spec or {}, fps
        context = context or {}
        self.n = len(scene.parts)
        sc = scene
        self.box = []
        for k in range(self.n):
            P = sc.T[k].reshape(-1, 3)
            self.box.append((P.min(0), P.max(0)) if len(P) else (sc.centre, sc.centre))
        self.ctr = [(lo + hi) / 2 for lo, hi in self.box]
        self.R = sc.radius
        # the electronics' own box: the camera closes in on it in chapter 1
        el = [k for k, p in enumerate(sc.parts) if p.get("kind") in ("board", "module", "cable")]
        if el:
            lo = np.min([self.box[k][0] for k in el], 0)
            hi = np.max([self.box[k][1] for k in el], 0)
            self.e_ctr = (lo + hi) / 2
            self.e_zoom = clamp(0.85 * self.R / max(float(np.linalg.norm(hi - lo)) / 2, 1e-6), 1.0, 2.0)
        else:
            self.e_ctr, self.e_zoom = sc.centre, 1.0
        self.accent = hexrgb(self.spec.get("accent")) or (0.16, 0.74, 0.62)
        self._motions()
        self._steps(context.get("fitted_after") or [])
        self._fx()
        self._clock()

    # ------------------------------------------------------------ order
    def _steps(self, fitted_after):
        parts = self.scene.parts
        caps = {str(k).lower(): str(v) for k, v in (self.spec.get("captions") or {}).items()}

        def cap(k, default=""):
            return caps.get(str(parts[k].get("label")).lower(), default)

        board = [k for k, p in enumerate(parts) if p.get("kind") == "board"]
        modules = [k for k, p in enumerate(parts) if p.get("kind") == "module"]
        cables = [k for k, p in enumerate(parts) if p.get("kind") == "cable"]
        bodies = [k for k, p in enumerate(parts) if p.get("kind") not in ("board", "module", "cable")]
        modules.sort(key=lambda k: (min(parts[k].get("ports") or [99]), parts[k].get("label")))
        mod_rank = {parts[k].get("label"): i for i, k in enumerate(modules)}
        cables.sort(key=lambda k: mod_rank.get(parts[k].get("cable_of"), 99))
        fa = {str(x).lower(): i for i, x in enumerate(fitted_after)}

        def body_key(k):
            lab = str(parts[k].get("label")).lower()
            lo = self.box[k][0]
            if lab in fa:
                return (1, fa[lab], 0.0)
            # not declared as fitted later: fixed / base parts, bottom up
            return (0, 0, float(lo[2]))
        fasteners = [k for k in bodies if FASTENER.search(str(parts[k].get("label")))]
        main = sorted([k for k in bodies if k not in fasteners], key=body_key)
        fasteners.sort(key=body_key)
        steps = []
        total_e = len(board) + len(modules) + len(cables)
        chapter = "Electronics" if total_e else None
        for k in board:
            steps.append(Step("drop", [k], 1.35, parts[k].get("name") or "Atech board",
                              cap(k, "The brain: every module plugs in here"), chapter))
            chapter = None
        for k in modules:
            p = parts[k]
            ports = p.get("ports") or []
            sub = cap(k, ("Port %s" % "+".join(str(x) for x in ports)) if ports else "")
            steps.append(Step("slide", [k], 0.8, p.get("name") or pretty(p.get("label")), sub, chapter))
            chapter = None
        for k in cables:
            p = parts[k]
            to = p.get("cable_to") or ""
            steps.append(Step("grow", [k], 0.95, "Cable" + (" to %s" % to if to else ""),
                              cap(k, "Routed inside the body"), chapter))
            chapter = None
        chapter = "Body"
        for grp in self._groups(main):
            k = grp[0]
            n = len(grp)
            title = pretty(group_key(parts[k].get("label")) if n > 1 else parts[k].get("label"))
            if n > 1:
                title += "  x%d" % n
            ext = float(np.linalg.norm(self.box[k][1] - self.box[k][0]))
            big = clamp(ext / (2 * self.R))
            st = Step("fly", grp, (0.85 + 0.35 * big) if n == 1 else min(0.9 + 0.16 * (n - 1), 1.9),
                      title, cap(k, _colour_words(parts[k])), chapter)
            st.stagger = 0.16 if n > 1 else 0.0
            steps.append(st)
            chapter = None
        chapter = "Fasteners"
        for grp in self._groups(fasteners, by_kind=True):
            k = grp[0]
            n = len(grp)
            title = pretty(group_key(parts[k].get("label")) if n > 1 else parts[k].get("label"))
            if n > 1:
                title += "  x%d" % n
            st = Step("screw", grp, min(1.0 + 0.2 * (n - 1), 2.2), title,
                      cap(k, "Driven home"), chapter)
            st.stagger = 0.2 if n > 1 else 0.0
            steps.append(st)
            chapter = None
        # keep the assembly near its budget: long builds go a little faster
        budget = float(self.spec.get("assembly_seconds") or 17.0)
        total = sum(s.dur for s in steps)
        if total > budget:
            f = max(0.55, budget / total)
            for s in steps:
                s.dur *= f
                s.stagger *= f
        self.steps = steps
        self.order = [k for s in steps for k in s.parts]

    def _groups(self, ks, by_kind=False):
        """Consecutive parts of one name (Rubber_1..4) as one step."""
        out = []
        for k in ks:
            key = group_key(self.scene.parts[k].get("label"))
            if out and group_key(self.scene.parts[out[-1][0]].get("label")) == key:
                out[-1].append(k)
            else:
                out.append([k])
        if by_kind:              # all fasteners of a kind together, wherever they were
            merged = {}
            for g in out:
                merged.setdefault(group_key(self.scene.parts[g[0]].get("label")), []).extend(g)
            out = list(merged.values())
        return out

    # ------------------------------------------------------------ motion
    def _motions(self):
        """Per part: where it comes from (offset), how it turns on the
        way, and for cables the growth axis."""
        sc, R = self.scene, self.R
        mid = sc.centre
        self.away, self.tumble, self.grow = {}, {}, {}
        rng = np.random.default_rng(11)
        for k, p in enumerate(sc.parts):
            kind = p.get("kind")
            c = self.ctr[k]
            lab = str(p.get("label"))
            if kind == "board":
                self.away[k] = np.array([0.0, 0.0, 1.7 * R])
                self.tumble[k] = (np.array([0.0, 0.0, 1.0]), 70.0)
            elif kind == "module":
                a = np.asarray(p.get("slide_axis") or (0, 0, -1), float)
                if np.linalg.norm(a) < 1e-6:
                    a = np.array([0.0, 0.0, -1.0])
                a = a / np.linalg.norm(a)
                travel = max(float(p.get("slide_out") or 0) * 4.0, 0.75 * R)
                if float(p.get("slide_out") or 0) <= 0:      # cabled: drop in from above
                    a = np.array([0.0, 0.0, -1.0])
                self.away[k] = -a * travel
                self.tumble[k] = (np.array([0.0, 0.0, 1.0]), 0.0)
            elif kind == "cable":
                T = sc.T[k]
                ax = _pca_axis(T)
                P = T.reshape(-1, 3)
                s = P @ ax
                lo, hi = float(s.min()), float(s.max())
                # grow from the end nearer the board (the middle of the electronics)
                if abs(lo - float(mid @ ax)) > abs(hi - float(mid @ ax)):
                    ax, lo, hi = -ax, -hi, -lo
                self.grow[k] = (ax, lo, hi)
                self.away[k] = np.zeros(3)
                self.tumble[k] = (np.array([0.0, 0.0, 1.0]), 0.0)
            elif FASTENER.search(lab):
                lo, hi = self.box[k]
                ax = _pca_axis(sc.T[k])
                if float(ax @ (c - mid)) < 0:
                    ax = -ax
                length = float(np.linalg.norm(hi - lo))
                self.away[k] = ax * max(5.0 * length, 0.35 * R)
                self.tumble[k] = (ax, 900.0)                 # spins in
                self.screw_axis = getattr(self, "screw_axis", {})
                self.screw_axis[k] = ax
            else:
                d = c - mid
                d[2] = max(d[2], 0.0) + 0.55 * np.linalg.norm(d[:2]) + 0.35 * R
                if FOOT.search(lab):                         # feet come from the side
                    d = c - mid
                    d[2] = 0.0
                if np.linalg.norm(d) < 1e-6:
                    d = np.array([0.0, 0.0, 1.0])
                d = d / np.linalg.norm(d)
                self.away[k] = d * 1.9 * R
                ax = rng.normal(size=3)
                self.tumble[k] = (ax / np.linalg.norm(ax), float(rng.uniform(35, 70)))

    def _fx(self):
        """Spinning and glowing parts (the director's, else by name)."""
        parts = self.scene.parts
        by_label = {str(p.get("label")).lower(): k for k, p in enumerate(parts)}
        self.spin, self.glow = {}, {}
        spins = self.spec.get("spin")
        if isinstance(spins, list) and spins:
            for s in spins:
                if not isinstance(s, dict):
                    continue
                k = by_label.get(str(s.get("part", "")).lower())
                if k is None:
                    continue
                ax = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}.get(str(s.get("axis", "")).lower())
                ax = np.array(ax, float) if ax else _thin_axis(*self.box[k])
                self.spin[k] = (ax, clamp(float(s.get("speed", 1.0) or 1.0), 0.1, 3.0))
        else:
            for k, p in enumerate(parts):
                if p.get("kind") in ("board", "module", "cable"):
                    continue
                if SPINNER.search(str(p.get("label"))) and not FASTENER.search(str(p.get("label"))):
                    self.spin[k] = (_thin_axis(*self.box[k]), 1.0)
        glows = self.spec.get("glow")
        if isinstance(glows, list) and glows:
            for g in glows:
                if not isinstance(g, dict):
                    continue
                k = by_label.get(str(g.get("part", "")).lower())
                if k is not None:
                    self.glow[k] = hexrgb(g.get("color")) or tuple(self.scene.colors[k])
        else:
            for k, p in enumerate(parts):
                if p.get("kind") in ("board", "module", "cable"):
                    continue
                lab = str(p.get("label"))
                if FASTENER.search(lab):
                    continue
                if (float(p.get("transparency") or 0) > 5 and GLOWER.search(lab)) or \
                        re.search(r"(glow|lens|diffuser|halo)", lab, re.I):
                    c = np.asarray(self.scene.colors[k], float)
                    self.glow[k] = tuple(np.clip(c * 0.6 + np.array([1.0, 0.92, 0.7]) * 0.4, 0, 1))

    # ------------------------------------------------------------ clock
    def _clock(self):
        self.t_hero = 2.0
        self.t_scatter = 0.9
        self.t_gap = 0.35
        t = self.t_hero + self.t_scatter + self.t_gap
        self.t_asm0 = t
        for s in self.steps:
            s.t0 = t
            t += s.dur
        self.t_asm1 = t
        self.t_settle = 0.75
        self.t_fin0 = t + self.t_settle
        self.t_finale = 4.6
        self.t_end = self.t_fin0 + self.t_finale
        self.frames = int(math.ceil(self.t_end * self.fps))
        az = self.spec.get("hero_az")
        try:
            az = float(az)
        except (TypeError, ValueError):
            az = 32.0
        self.az = az

    # ------------------------------------------------------------ frames
    def camera(self, t):
        az0 = self.az
        if t < self.t_hero:
            x = ease_out(t / self.t_hero, 2)
            return render.camera(self.scene, lerp(az0 + 75, az0 + 18, x), lerp(13, 18, x),
                                 lerp(1.45, 1.32, x))
        t1 = self.t_hero + self.t_scatter + self.t_gap
        if t < t1:
            x = smooth((t - self.t_hero) / (t1 - self.t_hero))
            return render.camera(self.scene, lerp(az0 + 18, az0 - 8, x), lerp(18, 28, x),
                                 lerp(1.32, 1.22, x))
        if t < self.t_fin0:
            x = (t - t1) / max(self.t_fin0 - t1, 1e-6)
            e = self._elec_focus(t)
            return render.camera(self.scene, lerp(az0 - 8, az0 + 42, smooth(x)),
                                 lerp(28, 25, x) + 8 * e, lerp(1.22, 1.3, x) * lerp(1.0, self.e_zoom, e),
                                 target=self.scene.centre + (self.e_ctr - self.scene.centre) * e)
        x = (t - self.t_fin0) / self.t_finale
        return render.camera(self.scene, lerp(az0 + 42, az0 + 42 + 320, ease_in_out(x)),
                             lerp(25, 11, smooth(x)), lerp(1.3, 1.4, smooth(x)))

    def _elec_focus(self, t):
        """0..1: how far the camera has closed in on the electronics."""
        body = [s.t0 for s in self.steps if s.kind not in ("drop", "slide", "grow")]
        if not self.steps or self.steps[0].kind not in ("drop", "slide", "grow"):
            return 0.0
        t_in = self.t_asm0 - 0.1
        t_out = body[0] if body else self.t_asm1
        return smooth((t - t_in) / 0.6) * (1 - smooth((t - t_out + 0.2) / 0.9))

    def _spun(self, xf, t, speed_k):
        for k, (ax, sp) in self.spin.items():
            if xf.get(k, {}).get("hidden"):
                continue
            ang = speed_k * sp
            if ang == 0:
                continue
            lo, hi = self.box[k]
            x = dict(xf.get(k) or {})
            R0 = render.rot(ax, ang)
            if x.get("R") is not None:
                x["R"] = x["R"] @ R0
            else:
                x["R"] = R0
                x["pivot"] = (lo + hi) / 2
            xf[k] = x

    def _spin_angle(self, t):
        """Degrees turned by a speed-1 spinner at t (hero and finale only)."""
        if t < self.t_hero + self.t_scatter:
            return 210.0 * t
        if t < self.t_fin0:
            return 0.0
        u = t - self.t_fin0
        ramp = 0.9                      # spin up over this long
        if u < ramp:
            return 210.0 * u * u / (2 * ramp)
        return 210.0 * (ramp / 2 + (u - ramp))

    def _place(self, k, x, kind):
        """Pose of part k at progress x of its own arrival (0 away, 1 home)."""
        off = self.away.get(k, np.zeros(3))
        ax, deg = self.tumble.get(k, (np.array([0, 0, 1.0]), 0.0))
        if kind == "drop":
            e = ease_bounce(x)
        elif kind == "slide":
            e = ease_back(x, 1.2)
        elif kind == "screw":
            e = ease_out(x, 3)
        else:
            e = ease_back(x, 1.35)
        out = {"t": off * (1 - e)}
        spin = deg * (1 - ease_out(x, 2))
        if spin:
            lo, hi = self.box[k]
            out["R"] = render.rot(ax, spin)
            out["pivot"] = (lo + hi) / 2
        return out

    def state(self, f):
        """Everything frame f shows: dict(t, cam, xf, glow, overlays...)."""
        t = f / float(self.fps)
        cam = self.camera(t)
        xf, glow = {}, {}
        info = {"t": t, "cam": cam, "xf": xf, "glow": glow, "step": None, "chapter": None,
                "rings": [], "confetti": None, "title": 0.0, "end": 0.0, "progress": None,
                "phase": "hero"}
        hero_end = self.t_hero
        scat_end = self.t_hero + self.t_scatter
        if t < hero_end:
            info["title"] = clamp((t - 0.25) / 0.45) * (1 - clamp((t - hero_end + 0.35) / 0.35))
            self._spun(xf, t, self._spin_angle(t))
            for k, c in self.glow.items():
                glow[k] = tuple(np.asarray(c) * 0.9)
            info["shadow_key"] = "home"
            return info
        if t < scat_end:
            info["phase"] = "scatter"
            x = (t - hero_end) / self.t_scatter
            rank = {k: i for i, k in enumerate(self.order)}
            for k in range(self.n):
                # last fitted leaves first
                i = rank.get(k, 0)
                d = 0.45 * (1 - i / max(len(self.order) - 1, 1))
                y = ease_in(clamp((x - d) / 0.55), 2)
                if y >= 1:
                    xf[k] = {"hidden": True}
                    continue
                pose = self._place(k, 1 - y, "fly")
                pose["t"] = self._scatter_off(k) * y
                xf[k] = pose
            self._spun(xf, t, self._spin_angle(t))
            return info
        if t < self.t_asm0:
            info["phase"] = "gap"
            for k in range(self.n):
                xf[k] = {"hidden": True}
            info["chapter"] = (self.steps[0].chapter, clamp((t - scat_end) / 0.3)) \
                if self.steps and self.steps[0].chapter else None
            info["shadow_key"] = "empty"
            return info
        if t < self.t_asm1 + self.t_settle:
            info["phase"] = "assembly"
            cur = None
            chap = None
            for i, s in enumerate(self.steps):
                if s.chapter:
                    chap = (s.chapter, i)
                if t < s.t0:
                    for k in s.parts:
                        xf[k] = {"hidden": True}
                    continue
                if cur is None or t >= s.t0:
                    cur = (i, s)
                self._advance(s, t, xf, glow, info)
            if cur is not None and t < self.t_asm1:
                i, s = cur
                info["step"] = (i, s, clamp((t - s.t0) / 0.2), clamp((s.t0 + s.dur - t) / 0.15) if i == len(self.steps) - 1 else 1.0)
                info["progress"] = clamp((t - self.t_asm0) / max(self.t_asm1 - self.t_asm0, 1e-6))
            if chap is not None and t < self.t_asm1:
                name, i0 = chap
                s0 = self.steps[i0]
                nxt = [s.t0 for s in self.steps[i0 + 1:] if s.chapter]
                t_out = nxt[0] if nxt else self.t_asm1
                a = clamp((t - s0.t0 + 0.3) / 0.3) * clamp((t_out - t) / 0.25)
                info["chapter"] = (name, a)
            if t >= self.t_asm1:
                info["phase"] = "settle"
                u = t - self.t_asm1
                info["confetti"] = u
                info["flash"] = max(0.0, 1 - u / 0.35) * 0.35
                info["shadow_key"] = "home"
            return info
        # finale
        info["phase"] = "finale"
        u = t - self.t_fin0
        self._spun(xf, t, self._spin_angle(t))
        on = smooth(u / 0.6)
        pulse = 0.85 + 0.15 * math.sin(u * 5.0)
        for k, c in self.glow.items():
            glow[k] = tuple(np.asarray(c) * on * pulse)
        info["end"] = smooth((u - (self.t_finale - 2.3)) / 0.6)
        # the end card takes the lower third: the product rises above it
        cam["shift"] = 0.17 * info["end"]
        cam["zoom"] *= 1 - 0.28 * info["end"]
        info["confetti"] = (t - self.t_asm1) if u < 2.5 else None
        info["shadow_key"] = "home"
        return info

    def _scatter_off(self, k):
        off = self.away.get(k)
        if off is None or np.linalg.norm(off) < 1e-6 or self.scene.parts[k].get("kind") == "cable":
            d = self.ctr[k] - self.scene.centre
            d[2] = abs(d[2]) + 0.5 * self.R
            off = d / max(np.linalg.norm(d), 1e-6) * 2.2 * self.R
        return off * 1.6

    def _advance(self, s, t, xf, glow, info):
        n = len(s.parts)
        for j, k in enumerate(s.parts):
            t0 = s.t0 + j * s.stagger
            dur = max(s.dur - (n - 1) * s.stagger, 0.25)
            x = clamp((t - t0) / dur)
            if t < t0:
                xf[k] = {"hidden": True}
                continue
            if s.kind == "grow":
                ax, lo, hi = self.grow[k]
                e = ease_in_out(x)
                if e < 1:
                    p = ax * (lo + (hi - lo) * e)
                    xf[k] = {"clip": (p, ax)}
                if x < 1:
                    # the cable's growing tip glows
                    glow[k] = tuple(np.asarray(self.accent) * 0.55)
                continue
            if x < 1:
                xf[k] = self._place(k, x, s.kind)
            land = t - (t0 + dur)
            if 0 <= land < 0.5 and s.kind in ("drop", "slide", "screw"):
                glow[k] = tuple(np.asarray(self.accent) * 0.7 * (1 - land / 0.5))
                info["rings"].append((self.ctr[k], land / 0.5))
            elif 0 <= land < 0.25 and s.kind == "fly":
                info["rings"].append((self.ctr[k], 0.3 + land / 0.25 * 0.7))


def _colour_words(p):
    """A short material line from a part's colour (e.g. "Mint, printed")."""
    c = p.get("color") or (0.8, 0.8, 0.8)
    try:
        r, g, b = [float(x) for x in c[:3]]
    except (TypeError, ValueError):
        return ""
    if float(p.get("transparency") or 0) > 5:
        return "Translucent"
    mx, mn = max(r, g, b), min(r, g, b)
    if mx < 0.2:
        return "Black"
    if mx - mn < 0.07:
        return "White" if mx > 0.85 else ("Silver" if mx > 0.6 else "Graphite")
    h = _hue(r, g, b)
    for lim, name in ((15, "Red"), (40, "Orange"), (65, "Yellow"), (95, "Lime"),
                      (160, "Green"), (185, "Mint"), (215, "Sky blue"), (255, "Blue"),
                      (290, "Violet"), (335, "Pink"), (361, "Red")):
        if h < lim:
            return name
    return ""


def _hue(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d <= 0:
        return 0.0
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0
