"""shop - links to the Atech shop at atech.dev (R840).

Atelier names modules as models/presets.yaml does (`orientation`,
`scd40_air_quality`); the shop names its products by slug (`orientation-
sensor`, `co2-sensor`; the site's src/lib/pricing.ts). SHOP_SLUGS is the
one join between the two. A module with no slug (the PIR sensor, the
stepper driver, the parts without a port) is not sold on its own and never
goes in a cart link.

The cart link is the site's /cart?add=… (src/lib/cartLink.ts in the site):
shop slugs with an optional :count, plus from=atelier. The site sets each
line to at least that count, so opening the link twice does not double
the order.

R850, the 3D print voucher (the site's PRINT_VOUCHER, src/lib/pricing.ts):
one print up to 34 x 32 x 34 cm and 350 g, printed by Atech; $15 on its
own, one free with the Big Kit and three with the Chunky Kit. plan_prints()
packs a design's printed parts into as few vouchers as they need, from each
part's laid-flat size and an estimate of the filament it takes. Pure: the
parts are dicts (print_order.py measures them from a FreeCAD document).
"""
import json
import os
import uuid
from collections import Counter

#: $ATECH_SITE points the links and the print request at another site
#: (staging: https://staging.atech.dev)
SITE = (os.environ.get("ATECH_SITE") or "https://atech.dev").rstrip("/")
SHOP = SITE + "/modules"
BOARD = "motherboard_14_port"

#: presets.yaml name -> the shop's product slug
SHOP_SLUGS = {
    "motherboard_14_port": "frame-2",
    "button": "button",
    "light": "led-grid",
    "usbc": "usb-c",
    "screen": "screen",
    "big_screen": "big-screen",
    "speaker": "speaker",
    "microphone": "microphone",
    "dc_motor": "dc-motor",
    "orientation": "orientation-sensor",
    "temp_humidity": "temp-sensor",
    "distance_sensor": "distance-sensor",
    "knob": "knob",
    "scd40_air_quality": "co2-sensor",
    "soil_sensor": "soil-sensor",
    "camera": "camera",
    "robot_arm": "robot-arm",
    "power_jack": "power-jack",
    "load_cell": "load-cell",
}

#: the shop's own product names (the site's src/lib/pricing.ts)
SHOP_NAMES = {
    "frame-2": "14-Port Motherboard", "button": "Button", "led-grid": "Light Grid",
    "usb-c": "USB-C", "screen": "Screen", "big-screen": "Big Screen", "speaker": "Speaker",
    "microphone": "Microphone", "dc-motor": "DC Motor", "orientation-sensor": "Orientation Sensor",
    "temp-sensor": "Temp & Humidity", "distance-sensor": "Distance Sensor", "knob": "Knob",
    "co2-sensor": "CO\u2082 Sensor", "soil-sensor": "Soil Sensor", "camera": "Camera",
    "robot-arm": "Robot Arm Integrator", "power-jack": "Power Jack", "load-cell": "Load Cell",
    "print-voucher": "3D print voucher",
}

#: shop slugs with a product page but not yet in the cart ("coming soon")
COMING_SOON = {"load-cell"}

#: R850 the 3D print voucher: its slug and what one print may be (the
#: site's PRINT_VOUCHER and PRINT_VOUCHER_SIZE: "34 x 32 x 34" cm, 350 g; 500 g until 6 Nov 2026)
VOUCHER = "print-voucher"
VOUCHER_MM = (340.0, 320.0, 340.0)          # bed width, bed depth, height
VOUCHER_GRAMS = 350.0
VOUCHER_EMAIL = "hello@atech.dev"
#: R850 the voucher's popup on the site (what one covers, examples)
VOUCHER_URL = SITE + "/#print-voucher"
#: R850 where Send my prints posts the 3MFs (the site's /api/print-request)
PRINT_REQUEST_URL = SITE + "/api/print-request"
PRINT_REQUEST_MAX_FILES = 8
PRINT_REQUEST_MAX_BYTES = 18 * 1024 * 1024
#: free vouchers per kit (the site's KITS[...].printVouchers)
KIT_VOUCHERS = {"Small Kit": 0, "Big Kit": 1, "Chunky Kit": 3}

#: R850 filament estimate: PLA, two 0.4 mm walls plus top and bottom
#: (about 1 mm of skin over the whole surface) and 15 % infill inside
PLA_DENSITY = 1.24                          # g/cm3, as export_tools
SKIN_MM = 1.0
INFILL = 0.15
GAP_MM = 3.0                                # between parts on one bed
#: R850 a last print this light (share of the voucher's grams and bed)
#: is worth asking the agent to fold into the others
LIGHT_SHARE = 0.15


def slug(name):
    """The shop slug of a presets.yaml module name, or None."""
    return SHOP_SLUGS.get(name or "")


def module_url(name):
    """The module's page on atech.dev (what it does, its price, Add to
    cart), or the shop's module grid when it has none."""
    s = slug(name)
    return "%s/%s" % (SHOP, s) if s else SHOP


def bill(names, board=True):
    """(Counter {slug: count} that can go in the cart, [names not sold])
    for the modules in `names` (one entry per module on the board), with
    the board itself first when `board`."""
    want, unsold = Counter(), []
    for n in ([BOARD] if board else []) + list(names):
        s = slug(n)
        if s and s not in COMING_SOON:
            want[s] += 1
        elif n and n not in unsold:
            unsold.append(n)
    return want, unsold


def cart_url(names, board=True, prints=0):
    """The atech.dev cart with these modules (and the board) in it, and
    `prints` 3D print vouchers."""
    want, _unsold = bill(names, board)
    if prints and int(prints) > 0:
        want[VOUCHER] += int(prints)
    if not want:
        return SHOP
    items = ",".join(s if c == 1 else "%s:%d" % (s, c) for s, c in want.items())
    return "%s/cart?add=%s&from=atelier" % (SITE, items)


def quote(cart, timeout=8, opener=None):
    """What the cart at `cart` (a cart_url) costs, from the site's
    /api/quote: {"currency", "lines", "total": {"amount", "text"},
    "unknown", "kit": {...} | None}, in the visitor's currency. None when
    there is nothing to price or no answer (offline, an older site)."""
    import urllib.request
    if not cart.startswith(SITE + "/cart?"):
        return None
    req = urllib.request.Request(SITE + "/api/quote?" + cart.split("?", 1)[1],
                                 headers={"Accept": "application/json",
                                          "User-Agent": "AtechAtelier"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8") or "{}")
    except Exception:                                     # noqa: BLE001
        return None
    total = data.get("total") if isinstance(data, dict) else None
    if not isinstance(total, dict) or not total.get("text"):
        return None
    return data


def price_line(q):
    """"About 1,334 SEK on atech.dev, before shipping." and the kit the
    cart will offer, as the site words it (cart.link.kit / kitMore)."""
    if not q:
        return ""
    s = "About %s on atech.dev, before shipping." % q["total"]["text"]
    k = q.get("kit")
    if k:
        free = k.get("freeVouchers") or 0
        v = ("" if not free else " and a free 3D print voucher" if free == 1
             else " and %d free 3D print vouchers" % free)
        if (k.get("more") or {}).get("amount", 0) > 0:
            s += " For %s more, the %s has every module here, %d more modules%s." % (
                k["more"]["text"], k["name"], k.get("extra", 0), v)
        else:
            s += " Cheaper as the %s: every module here%s, for %s." % (
                k["name"], v, k["total"]["text"])
    return s


def open_url(url):
    """Open `url` in the user's browser. True when Qt took it."""
    from PySide6 import QtCore, QtGui
    return bool(QtGui.QDesktopServices.openUrl(QtCore.QUrl(url)))


# ===================================================================
# R850 the 3D print voucher
# ===================================================================
def print_grams(volume_mm3, area_mm2):
    """About how many grams of PLA a part prints with: its skin solid,
    the inside at the infill. A solid block's full mass would overstate a
    casing several times over; a thin shell prints nearly solid."""
    vol = max(0.0, float(volume_mm3))
    skin = min(vol, max(0.0, float(area_mm2)) * SKIN_MM)
    return (skin + INFILL * (vol - skin)) * PLA_DENSITY / 1000.0


def _fits_bed(w, d, bed=VOUCHER_MM):
    return (w <= bed[0] and d <= bed[1]) or (d <= bed[0] and w <= bed[1])


def _fits_diagonally(w, d, bed=VOUCHER_MM, step_deg=0.5):
    """A long footprint w x d turned on the bed so it fits corner to corner."""
    import math
    k = 0
    while k * step_deg <= 90.0:
        a = math.radians(k * step_deg)
        c, s = math.cos(a), math.sin(a)
        if w * c + d * s <= bed[0] and w * s + d * c <= bed[1]:
            return True
        k += 1
    return False


def fit(size, grams=0.0, bed=VOUCHER_MM, max_g=VOUCHER_GRAMS):
    """How a part of laid-flat `size` (w, d, h mm) fits one voucher:
    "ok", "on its side" (it fits stood another way up), "diagonal" (corner
    to corner on the bed), or "too big" / "too heavy" (split it). The last
    two ways take a print of their own."""
    w, d, h = (float(v) for v in size)
    if grams > max_g:
        return "too heavy"
    if h <= bed[2] and _fits_bed(w, d, bed):
        return "ok"
    if h <= bed[2] and _fits_diagonally(w, d, bed):
        return "diagonal"                   # still flat: better than standing up
    for a, b, c in ((w, h, d), (h, d, w)):
        if c <= bed[2] and _fits_bed(a, b, bed):
            return "on its side"
    for a, b, c in ((w, h, d), (h, d, w)):
        if c <= bed[2] and _fits_diagonally(a, b, bed):
            return "on its side"
    return "too big"


#: MaxRects placement rules _pack tries in turn: best short side fit,
#: best area fit, bottom-left; and part orders: biggest area, longest side
_RULES = ("short", "area", "bottom")
_ORDERS = (lambda t: -(t[0] * t[1]), lambda t: -max(t), lambda t: -min(t))


def _pack(items, bed=VOUCHER_MM, gap=GAP_MM):
    """Where footprints `items` [(w, d)] go on the bed, side by side and
    each turned either way: [(x, y, w, d)] in the order given, or None when
    they do not all fit. MaxRects with each placement rule and part order
    in turn until one fits; every part is kept `gap` from the next (not
    from the bed's edge)."""
    for key in _ORDERS:
        for rule in _RULES:
            out = _pack_once(items, bed, gap, rule, key)
            if out is not None:
                return out
    return None


def _pack_once(items, bed, gap, rule, key):
    free = [(0.0, 0.0, bed[0] + gap, bed[1] + gap)]
    order = sorted(range(len(items)), key=lambda i: key(items[i]))
    out = [None] * len(items)
    for i in order:
        a, b = items[i]
        best = None
        for fx, fy, fw, fh in free:
            for w, d in ((a, b), (b, a)):
                W, D = w + gap, d + gap
                if W <= fw + 1e-9 and D <= fh + 1e-9:
                    if rule == "short":
                        score = (min(fw - W, fh - D), max(fw - W, fh - D))
                    elif rule == "area":
                        score = (fw * fh - W * D, min(fw - W, fh - D))
                    else:
                        score = (fy + D, fx)
                    if best is None or score < best[0]:
                        best = (score, fx, fy, w, d)
        if best is None:
            return None
        _s, x, y, w, d = best
        out[i] = (x, y, w, d)
        used = (x, y, w + gap, d + gap)
        nxt = []
        for f in free:
            nxt.extend(_split(f, used))
        free = [f for f in nxt if not any(g is not f and _inside(f, g) for g in nxt)]
        # identical rectangles: keep one
        seen, uniq = set(), []
        for f in free:
            k = tuple(round(v, 6) for v in f)
            if k not in seen:
                seen.add(k)
                uniq.append(f)
        free = uniq
    return out


def _inside(a, b):
    return (a[0] >= b[0] - 1e-9 and a[1] >= b[1] - 1e-9 and a[0] + a[2] <= b[0] + b[2] + 1e-9
            and a[1] + a[3] <= b[1] + b[3] + 1e-9)


def _split(f, u):
    """The free rectangle f minus the used one u, as up to four maximal
    free rectangles (MaxRects)."""
    fx, fy, fw, fh = f
    ux, uy, uw, uh = u
    if ux >= fx + fw or ux + uw <= fx or uy >= fy + fh or uy + uh <= fy:
        return [f]
    out = []
    if ux > fx:
        out.append((fx, fy, ux - fx, fh))
    if ux + uw < fx + fw:
        out.append((ux + uw, fy, fx + fw - ux - uw, fh))
    if uy > fy:
        out.append((fx, fy, fw, uy - fy))
    if uy + uh < fy + fh:
        out.append((fx, uy + uh, fw, fy + fh - uy - uh))
    return out


def _shelves(items, bed=VOUCHER_MM, gap=GAP_MM):
    """True when footprints `items` [(w, d)] all fit on one bed (_pack)."""
    return _pack(items, bed, gap) is not None


def plan_prints(parts, bed=VOUCHER_MM, max_g=VOUCHER_GRAMS, gap=GAP_MM):
    """Pack printed parts into prints, one voucher each.

    parts: [{"label", "size": (w, d, h) laid flat, mm, "grams"}].
    Returns {"prints": [{"labels", "grams"}], "parts": [part + {"fit"}],
    "vouchers": n, "split": [labels too big or heavy for one voucher],
    "light": [labels of a last print so light the agent could fold it into
    the others], "grams": total}. Parts are placed biggest first, each on the first
    print it fits (bed area and weight); a part that only fits on its side
    (or diagonally) gets a print of its own."""
    rows, prints, split = [], [], []
    for p in parts:
        q = dict(p)
        q["fit"] = fit(p["size"], p.get("grams", 0.0), bed, max_g)
        rows.append(q)
    order = sorted((r for r in rows if r["fit"] in ("ok", "on its side", "diagonal")),
                   key=lambda r: -(r["size"][0] * r["size"][1]))
    for r in order:
        g = float(r.get("grams", 0.0))
        if r["fit"] != "ok":
            prints.append({"labels": [r["label"]], "grams": g, "foot": None})
            continue
        for pr in prints:
            if pr["foot"] is None or pr["grams"] + g > max_g:
                continue
            if _shelves(pr["foot"] + [tuple(r["size"][:2])], bed, gap):
                pr["foot"].append(tuple(r["size"][:2]))
                pr["labels"].append(r["label"])
                pr["grams"] += g
                break
        else:
            prints.append({"labels": [r["label"]], "grams": g, "foot": [tuple(r["size"][:2])]})
    split = [r["label"] for r in rows if r["fit"] in ("too big", "too heavy")]
    light = []
    if len(prints) > 1 and prints[-1]["foot"] is not None:
        last = prints[-1]
        area = sum(a * b for a, b in last["foot"])
        if last["grams"] <= LIGHT_SHARE * max_g and area <= LIGHT_SHARE * bed[0] * bed[1]:
            light = list(last["labels"])
    for pr in prints:
        pr.pop("foot", None)
        pr["grams"] = round(pr["grams"], 1)
    return {"prints": prints, "parts": rows, "vouchers": len(prints), "split": split,
            "light": light,
            "grams": round(sum(float(r.get("grams", 0.0)) for r in rows), 1)}


def plate(sizes, bed=VOUCHER_MM, gap=GAP_MM):
    """Where each laid-flat part of one print goes on the voucher's bed:
    [(cx, cy, turned)] (the part's centre, mm from the bed's corner; turned
    = a quarter turn about z), the parts together centred on the bed. A
    single part that only fits corner to corner is turned to its angle;
    returns None when they do not fit."""
    foot = [tuple(sz[:2]) for sz in sizes]
    pos = _pack(foot, bed, gap)
    if pos is None:
        return None
    x0 = min(p[0] for p in pos)
    y0 = min(p[1] for p in pos)
    x1 = max(p[0] + p[2] for p in pos)
    y1 = max(p[1] + p[3] for p in pos)
    dx, dy = (bed[0] - (x1 - x0)) / 2 - x0, (bed[1] - (y1 - y0)) / 2 - y0
    out = []
    for (x, y, w, d), (a, b) in zip(pos, foot):
        out.append((x + w / 2 + dx, y + d / 2 + dy, abs(w - a) > 1e-9 or abs(d - b) > 1e-9))
    return out


def diagonal_angle(w, d, bed=VOUCHER_MM, step_deg=0.5):
    """The turn (degrees) that fits a long w x d footprint corner to corner,
    or None."""
    import math
    k = 0
    while k * step_deg <= 90.0:
        a = math.radians(k * step_deg)
        c, s_ = math.cos(a), math.sin(a)
        if w * c + d * s_ <= bed[0] and w * s_ + d * c <= bed[1]:
            return k * step_deg
        k += 1
    return None


def kit_note(vouchers):
    """One plain sentence on the vouchers a design needs (the cart shows
    the price in the visitor's currency)."""
    n = int(vouchers)
    if n <= 0:
        return "Nothing to print: the design has no printed parts."
    if n == 1:
        return ("It prints on one 3D print voucher. The Big Kit comes with one free, "
                "the Chunky Kit with three.")
    if n <= 3:
        return ("It prints on %d 3D print vouchers. The Chunky Kit comes with three "
                "free, the Big Kit with one." % n)
    return ("It prints on %d 3D print vouchers. The Chunky Kit comes with three "
            "free." % n)


def mailto_url(subject, body, to=VOUCHER_EMAIL):
    """A mailto: link with the subject and body filled in."""
    from urllib.parse import quote
    return "mailto:%s?subject=%s&body=%s" % (to, quote(subject), quote(body))


def valid_email(text):
    import re
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$", (text or "").strip()))


def _multipart(fields, files, content_type="model/3mf"):
    """(body bytes, content type) of a multipart/form-data request; each
    file part labelled `content_type` (servers here read the bytes)."""
    b = "----atelier%s" % uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n" % (b, k)).encode()
                   + str(v).encode("utf-8") + b"\r\n")
    for path in files:
        name = os.path.basename(path).replace('"', "'")
        with open(path, "rb") as fh:
            data = fh.read()
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                    "Content-Type: %s\r\n\r\n" % (b, name, content_type)).encode("utf-8") + data + b"\r\n")
    out.append(("--%s--\r\n" % b).encode())
    return b"".join(out), "multipart/form-data; boundary=%s" % b


def send_print_request(email, files, design="", sheet="", note="", order="",
                       url=None, timeout=120, opener=None):
    """POST the prints to Atech (the site's /api/print-request). Returns
    {"ok", "status", "message"}; status 0 = no answer (offline), 503 = not
    open yet: both mean "send an email instead"."""
    import urllib.error
    import urllib.request
    if sum(os.path.getsize(f) for f in files) > PRINT_REQUEST_MAX_BYTES:
        return {"ok": False, "status": 413, "message": "The files are over 18 MB together."}
    body, ctype = _multipart({"email": email.strip(), "design": design, "sheet": sheet,
                              "note": note, "order": order}, files)
    req = urllib.request.Request(url or PRINT_REQUEST_URL, data=body, method="POST",
                                 headers={"Content-Type": ctype, "Accept": "application/json",
                                          "User-Agent": "AtechAtelier"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8") or "{}")
            return {"ok": bool(data.get("ok")), "status": r.status, "message": ""}
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8") or "{}").get("error", "")
        except Exception:                                 # noqa: BLE001
            msg = ""
        return {"ok": False, "status": e.code, "message": msg or str(e)}
    except Exception as e:                                # noqa: BLE001
        return {"ok": False, "status": 0, "message": str(e)}
