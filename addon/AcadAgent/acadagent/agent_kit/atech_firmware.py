"""atech_firmware - what an Atech product DOES, from the Atech SDK.

The CAD library (atech_ports) knows where a module sits. The Atech SDK
(`pip install atech`, https://github.com/atechdotdev/python-sdk) knows what
it does: its C++ API, the events it sends and the actions it takes, the
ports the firmware accepts it on, and its cautions. A product is both: the
model.py that seats the modules and a project.yaml that makes them work
(`atech build` / `atech upload` turn it into firmware). This file joins the
two halves:

    catalog()            the SDK catalog: the installed `atech` package when
                         it imports (the latest), else the snapshot shipped
                         beside this file (atech_sdk_catalog.json)
    SDK_ID               CAD module name -> SDK module id (None: no firmware)
    plan(seated)         seated modules [{"module", "ports"}] -> project.yaml
                         entries [{"id", "instance", "ports", "cad"}]
    issues(entries)      the SDK's placement rules on those entries
    project_yaml(...)    the text of a project.yaml
    read_project(path)   a project.yaml as a dict (PyYAML, or a small reader)
    compare(project, entries)  a written project.yaml against the build
    lint_code(project)   the SDK guide's rules for the code: block
    reference_md()       reference/ATECH_FIRMWARE.md

    python3 atech_firmware.py --sync       rewrite the snapshot from the
                                           installed SDK (needs `atech`), e.g.
        uv run --no-project --python 3.12 --prerelease=allow --with atech \
            python atech_firmware.py --sync
    python3 atech_firmware.py --reference  print ATECH_FIRMWARE.md

Python 3.9+, no third-party imports ($ATECH_SDK_CATALOG=snapshot skips the
installed SDK, for reproducible tests).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = os.path.join(HERE, "atech_sdk_catalog.json")
PROJECT = "project.yaml"
BOARD = "14port"             # the CAD library's board (motherboard_14_port)
REFERENCE = "ATECH_FIRMWARE.md"

#: CAD module name (presets.yaml) -> Atech SDK module id. None: the module
#: carries no firmware (the SDK guide: power modules need no entry).
SDK_ID = {
    "button": "button",
    "light": "neopixel",
    "screen": "st7735_tft",
    "speaker": "speaker",
    "microphone": "microphone",
    "dc_motor": "dc_motor",
    "orientation": "icm40608",
    "temp_humidity": "aht20",
    "distance_sensor": "distance_sensor",
    "knob": "rotary_encoder",
    "pir": "pir",
    "scd40_air_quality": "scd40_air_quality",
    "robot_arm": "robot_arm",
    "stepper_motor": "stepper_motor",
    "usbc": None,
}

#: SDK id -> the instance name plan() gives (btn, btn2, ...).
INSTANCE = {
    "button": "btn", "neopixel": "led", "st7735_tft": "screen",
    "speaker": "spk", "microphone": "mic", "dc_motor": "motor",
    "icm40608": "imu", "aht20": "th", "distance_sensor": "tof",
    "rotary_encoder": "knob", "stepper_motor": "stepper", "pir": "pir",
    "scd40_air_quality": "co2", "robot_arm": "arm",
}

_CATALOG = {}                # "cat" -> the loaded catalog


# ------------------------------------------------------------------ catalog
def _port_no(port_id):
    m = re.match(r"port_(\d+)$", str(port_id))
    return int(m.group(1)) if m else None


def _methods(*texts):
    """Method names the SDK documents: `{{ instance }}.name(` in usage, and
    the `name(` declarations of the driver header."""
    out = set()
    for t in texts:
        out.update(re.findall(r"\{\{\s*instance\s*\}\}\.(\w+)\s*\(", t or ""))
        for line in (t or "").splitlines():
            m = re.match(r"\s*(?:[\w:<>\*&]+\s+)+\*?&?(\w+)\s*\([^;{]*\)\s*"
                         r"(?:const\s*)?(?:override\s*)?[;{]", line)
            if m and m.group(1) not in ("if", "while", "for", "return", "switch"):
                out.add(m.group(1))
    # private helpers (_name) and constructors (ClassName) are not the API
    return sorted(n for n in out if not n.startswith("_") and not n[0].isupper())


def from_sdk(atech):
    """The catalog dict, read from an imported `atech` package."""
    import importlib.metadata as md
    root = os.path.dirname(atech.__file__)
    guide = ""
    try:
        with open(os.path.join(root, "docs", "guide.md"), encoding="utf-8") as fh:
            guide = fh.read()
    except OSError:
        pass
    boards = {}
    for b in atech.list_boards():
        boards[b.id] = {
            "name": b.name,
            "reserved": sorted(n for n in map(_port_no, b.reserved) if n),
            "ports": {str(p.slot_number): list(p.compatible_interfaces)
                      for p in b.ports if p.slot_number and p.id not in b.reserved},
            "adjacent": [sorted([_port_no(a), _port_no(c)])
                         for a, c in b.adjacent_port_pairs],
            "layout": [list(r) for r in b.layout],
        }
    mods = {}
    for m in atech.list_modules():
        header = ""
        try:
            with open(os.path.join(root, "catalog", "data", "modules", m.id,
                                   m.driver.header), encoding="utf-8") as fh:
                header = fh.read()
        except OSError:
            pass
        mods[m.id] = {
            "name": m.name, "category": m.category, "interface": m.interface,
            "size": m.size, "description": (m.description or "").strip(),
            "caution": (m.caution or "").strip(),
            "usage": (m.usage or "").strip(),
            "class": m.driver.class_name,
            "methods": _methods(m.usage, header),
            "events": [{"key": e.key, "type": e.type, "value_type": e.value_type,
                        "unit": e.unit, "description": e.description or ""}
                       for e in m.events],
            "actions": [{"key": a.key, "value_type": a.value_type,
                         "description": a.description or ""} for a in m.actions],
        }
    try:
        version = md.version("atech")
    except md.PackageNotFoundError:
        version = getattr(atech, "__version__", "unknown")
    return {"sdk_version": version, "guide": guide,
            "boards": boards, "modules": mods}


def _snapshot():
    with open(SNAPSHOT, encoding="utf-8") as fh:
        cat = json.load(fh)
    cat["source"] = "snapshot"
    return cat


def catalog(refresh=False):
    """The SDK catalog. The installed `atech` package wins (the latest
    info); without it, or with $ATECH_SDK_CATALOG=snapshot, the snapshot.
    None when neither is there."""
    if refresh:
        _CATALOG.clear()
    if "cat" in _CATALOG:
        return _CATALOG["cat"]
    cat = None
    if os.environ.get("ATECH_SDK_CATALOG") != "snapshot":
        try:
            import atech
            cat = from_sdk(atech)
            cat["source"] = "installed"
        except Exception:                              # noqa: BLE001
            cat = None
    if cat is None:
        try:
            cat = _snapshot()
        except (OSError, ValueError):
            cat = None
    _CATALOG["cat"] = cat
    return cat


def sdk_label(cat=None):
    cat = cat or catalog()
    if not cat:
        return "Atech SDK (not available)"
    return "Atech SDK %s (%s)" % (cat.get("sdk_version"), cat.get("source"))


# ------------------------------------------------------------------ plan
def plan(seated, cat=None):
    """project.yaml module entries for the modules a build seats or cables:
    [{"id", "instance", "ports", "cad"}] in port order. A module without
    firmware (usbc) is left out; a CAD name the map does not know gets
    id None (issues() reports it)."""
    cat = cat or catalog() or {"modules": {}}
    rows = sorted(seated, key=lambda m: min(m.get("ports") or [99]))
    used, out = {}, []
    for m in rows:
        name = str(m.get("module") or "")
        if name in SDK_ID and SDK_ID[name] is None:
            continue
        sid = SDK_ID.get(name)
        if sid is None and name in cat["modules"]:
            sid = name                       # the SDK and CAD share the id
        base = INSTANCE.get(sid, re.sub(r"\W", "_", name) or "module")
        used[base] = used.get(base, 0) + 1
        inst = base if used[base] == 1 else "%s%d" % (base, used[base])
        out.append({"id": sid, "instance": inst, "cad": name,
                    "ports": sorted(int(p) for p in m.get("ports") or ())})
    return out


def issues(entries, board=BOARD, cat=None):
    """The SDK's placement rules (atech.placement.validate) on entries:
    a list of plain sentences, empty when the SDK would build them."""
    cat = cat or catalog()
    if not cat:
        return []
    b = cat["boards"].get(board)
    if b is None:
        return ["board %r is not in the %s (boards: %s)"
                % (board, sdk_label(cat), ", ".join(sorted(cat["boards"])))]
    free = ", ".join(sorted(b["ports"], key=int))
    pairs = {tuple(p) for p in b["adjacent"]}
    out, taken = [], {}
    for e in entries:
        who = "%s (%s)" % (e.get("instance"), e.get("cad") or e.get("id"))
        spec = cat["modules"].get(e.get("id")) if e.get("id") else None
        if spec is None:
            out.append("%s has no firmware module in the %s: no project.yaml "
                       "entry can drive it" % (who, sdk_label(cat)))
            continue
        ports = list(e.get("ports") or ())
        for p in ports:
            if p in b["reserved"]:
                out.append("%s: port %d is reserved on the %s in the %s - the "
                           "firmware cannot drive a module there. Ports that "
                           "take modules: %s" % (who, p, board, sdk_label(cat), free))
            elif str(p) not in b["ports"]:
                out.append("%s: port %d does not exist on the %s" % (who, p, board))
            else:
                iface = set(b["ports"][str(p)])
                if spec["interface"] == "gpio":
                    iface |= {"gpio", "digital"}
                if spec["interface"] not in iface:
                    ok = [n for n, i in sorted(b["ports"].items(), key=lambda x: int(x[0]))
                          if spec["interface"] in i]
                    out.append("%s needs %s but port %d has %s; ports with %s: %s"
                               % (who, spec["interface"], p, "/".join(sorted(iface)),
                                  spec["interface"], ", ".join(ok) or "none"))
            if p in taken and taken[p] != e.get("instance"):
                out.append("%s: port %d is already used by %s" % (who, p, taken[p]))
            taken[p] = e.get("instance")
        if len(ports) != spec["size"]:
            out.append("%s takes %d port(s) in the SDK, the build gives it %d"
                       % (who, spec["size"], len(ports)))
        elif spec["size"] == 2 and tuple(sorted(ports)) not in pairs:
            out.append("%s: ports %d+%d are not a 2-port pair in the SDK; pairs: %s"
                       % (who, ports[0], ports[1],
                          " ".join("%d+%d" % tuple(q) for q in sorted(pairs))))
    return out


# ------------------------------------------------------------------ project.yaml
def _block(text, indent):
    lines = (text or "").rstrip("\n").splitlines() or [""]
    return "\n".join((" " * indent + l) if l.strip() else "" for l in lines)


def project_yaml(name, entries, setup="", loop="", board=BOARD):
    """The text of a project.yaml for `atech build` (the SDK guide's form)."""
    out = ["name: %s" % (re.sub(r"[^\w-]", "_", name or "product") or "product"),
           "board: %s" % board, "modules:"]
    for e in entries:
        if not e.get("id"):
            continue
        ports = e["ports"]
        where = ("port: %d" % ports[0] if len(ports) == 1
                 else "ports: [%s]" % ", ".join(str(p) for p in ports))
        out.append("  - {id: %s, instance: %s, %s}" % (e["id"], e["instance"], where))
    out += ["code:", "  setup: |", _block(setup or "// runs once after every module is initialised", 4),
            "  loop: |", _block(loop or "// runs forever - never block, use millis()", 4)]
    return "\n".join(out) + "\n"


def _scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    if re.match(r"-?\d+$", v):
        return int(v)
    if v.startswith("[") and v.endswith("]"):
        return [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
    return v


def _flow_map(text):
    """{id: x, instance: y, ports: [1, 2]} without PyYAML."""
    body, out, depth, cur = text.strip()[1:-1], {}, 0, ""
    parts = []
    for ch in body:
        depth += (ch == "[") - (ch == "]")
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    for p in parts:
        if ":" in p:
            k, v = p.split(":", 1)
            out[k.strip()] = _scalar(v)
    return out


def _parse(text):
    """The small subset of YAML a project.yaml uses (PyYAML is not in every
    Python that runs this): top-level scalars, `modules:` as flow or block
    mappings, `code:` with `setup: |` / `loop: |` block scalars."""
    data, lines, i = {}, text.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#") or line[0] == " ":
            continue
        key, _, rest = line.partition(":")
        key, rest = key.strip(), rest.split(" #")[0].strip()
        if rest:
            data[key] = _scalar(rest)
            continue
        if key == "modules":
            mods = []
            while i < len(lines) and (not lines[i].strip() or lines[i][0] == " "):
                s = lines[i].strip()
                i += 1
                if s.startswith("- {"):
                    mods.append(_flow_map(s[2:]))
                elif s.startswith("- "):
                    mods.append({})
                    k, _, v = s[2:].partition(":")
                    mods[-1][k.strip()] = _scalar(v)
                elif ":" in s and mods:
                    k, _, v = s.partition(":")
                    mods[-1][k.strip()] = _scalar(v)
            data[key] = mods
        elif key == "code":
            code = {}
            while i < len(lines) and (not lines[i].strip() or lines[i][0] == " "):
                m = re.match(r"(\s+)(\w+):\s*\|[-+]?\s*$", lines[i])
                i += 1
                if not m:
                    continue
                ind, body = len(m.group(1)), []
                while i < len(lines) and (not lines[i].strip()
                                          or len(lines[i]) - len(lines[i].lstrip()) > ind):
                    body.append(lines[i])
                    i += 1
                strip = min((len(l) - len(l.lstrip()) for l in body if l.strip()),
                            default=0)
                code[m.group(2)] = "\n".join(l[strip:] for l in body).strip("\n") + "\n"
            data[key] = code
    return data


def read_project(path):
    """project.yaml as a dict; raises ValueError when it cannot be read."""
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        import yaml
    except ImportError:
        yaml = None
    if yaml is not None:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError("project.yaml is not valid YAML: %s" % exc)
    else:
        data = _parse(text)
    if not isinstance(data, dict):
        raise ValueError("project.yaml must be a mapping (name:, board:, modules:, code:)")
    return data


def _entry_ports(m):
    p = m.get("ports", m.get("port"))
    if isinstance(p, (int, str)):
        p = [p]
    out = []
    for x in p or ():
        n = _port_no(x) if isinstance(x, str) and not x.isdigit() else int(x)
        if n is not None:
            out.append(n)
    return sorted(out)


def compare(project, entries, board=BOARD):
    """project.yaml against the modules the build placed: sentences, empty
    when every module is there on the build's ports (and nothing else)."""
    out = []
    if str(project.get("board", "")) != board:
        out.append("project.yaml board is %r; the CAD board is the %s"
                   % (project.get("board"), board))
    want = {(e["id"], tuple(e["ports"])): e for e in entries if e.get("id")}
    have = {}
    for m in project.get("modules") or ():
        if isinstance(m, dict):
            have[(str(m.get("id")), tuple(_entry_ports(m)))] = m
    for k, e in sorted(want.items(), key=lambda kv: kv[0][1]):
        if k not in have:
            alt = [h for h in have if h[0] == k[0]]
            out.append("project.yaml has no %s on port(s) %s (the build's %s)%s"
                       % (k[0], "+".join(map(str, k[1])), e["cad"],
                          "; it has it on %s" % ", ".join("+".join(map(str, h[1]))
                                                          for h in alt) if alt else ""))
    for k in sorted(have, key=lambda kv: kv[1]):
        if k not in want and not any(w[0] == k[0] for w in want):
            out.append("project.yaml lists %s on port(s) %s, which the build does "
                       "not place" % (k[0], "+".join(map(str, k[1]))))
    return out


def lint_code(project, cat=None):
    """The SDK guide's rules for the code: block, as sentences."""
    cat = cat or catalog() or {"modules": {}}
    code = project.get("code") or {}
    text = "\n".join(str(code.get(k) or "") for k in ("setup", "loop")) \
        if isinstance(code, dict) else ""
    out = []
    if not text.strip() or not re.search(r"[^\s/]", re.sub(r"//[^\n]*", "", text)):
        out.append("project.yaml code: is empty - the product does nothing; "
                   "make its modules do the product's job in loop:")
        return out
    if re.search(r"\bSerial\s*\.\s*(read\w*|available|peek|parse\w*)\s*\(", text):
        out.append("code: reads Serial - the firmware reads it for the laptop's "
                   "actions; use atech_action / atech_value instead")
    for d in re.findall(r"\bdelay\s*\(\s*(\d+)\s*\)", text):
        if int(d) > 10:
            out.append("code: delay(%s) blocks the loop - time it with millis()" % d)
            break
    if re.search(r"\b(pinMode|digitalWrite|digitalRead|analogRead|analogWrite)"
                 r"\s*\(\s*\d+", text):
        out.append("code: uses a GPIO number - pins come from the port; call the "
                   "module's methods")
    inst = {}
    for m in project.get("modules") or ():
        if isinstance(m, dict) and m.get("instance"):
            inst[str(m["instance"])] = str(m.get("id"))
    for name, mid in sorted(inst.items()):
        spec = cat["modules"].get(mid)
        if not spec or not spec.get("methods"):
            continue
        for meth in sorted(set(re.findall(r"\b%s\s*\.\s*(\w+)\s*\(" % re.escape(name), text))):
            if meth not in spec["methods"]:
                out.append("code: %s.%s() is not in the SDK's %s API (%s)"
                           % (name, meth, mid, ", ".join(spec["methods"][:12])))
    return out


# ------------------------------------------------------------------ reference
def _guide_section(guide, heading):
    m = re.search(r"^## %s\s*$(.*?)(?=^## |\Z)" % re.escape(heading), guide or "",
                  re.M | re.S)
    return m.group(1).strip() if m else ""


def _named(text, inst):
    return re.sub(r"\{\{\s*instance\s*\}\}", inst, text or "")


def reference_md(cat=None):
    """reference/ATECH_FIRMWARE.md: the firmware half of every module."""
    cat = cat or catalog()
    if not cat:
        return ""
    b = cat["boards"].get(BOARD) or {}
    mods = cat["modules"]
    cad_of = {v: k for k, v in SDK_ID.items() if v}
    out = ["# Atech firmware reference (%s)" % sdk_label(cat), "",
           "model.py places the modules; **project.yaml** makes them work. The "
           "Atech SDK turns project.yaml into firmware (`atech build`, `atech "
           "upload`). Every module in model.py that has an SDK id below gets "
           "one project.yaml entry on the SAME port(s), and the `code:` block "
           "makes the product do its job. Never invent a module, a method, an "
           "event or an action: this file is the SDK's own catalog. In Atelier "
           "the ports come from model.py (the user assembles the product to "
           "match), so where the SDK guide says to ask the user which port, "
           "read it from your build instead.", "",
           "## CAD module -> SDK module", "",
           "| CAD (model.py) | SDK id (project.yaml) | Ports | Events | Actions |",
           "|---|---|---|---|---|"]
    for cad, sid in sorted(SDK_ID.items()):
        if sid is None:
            out.append("| %s | - (power; no entry) | - | - | - |" % cad)
            continue
        s = mods.get(sid)
        if s is None:
            out.append("| %s | %s (not in this SDK) | - | - | - |" % (cad, sid))
            continue
        inst = INSTANCE.get(sid, sid)
        out.append("| %s | %s | %d | %s | %s |" % (
            cad, sid, s["size"],
            ", ".join("`%s`" % _named(e["key"], inst) for e in s["events"]) or "-",
            ", ".join("`%s`" % _named(a["key"], inst) for a in s["actions"]) or "-"))
    extra = sorted(set(mods) - set(cad_of))
    if extra:
        out += ["", "SDK modules with no CAD model yet (model.py cannot place "
                "them): %s." % ", ".join("%s (%s)" % (m, mods[m]["name"]) for m in extra)]
    if b:
        out += ["", "## The %s board in the SDK" % BOARD, "",
                "- Ports that take modules: %s" % ", ".join(sorted(b["ports"], key=int)),
                "- Reserved (no module can be built there): %s"
                % (", ".join("port %d" % p for p in b["reserved"]) or "none"),
                "- 2-port modules need one of these pairs: %s"
                % " ".join("%d+%d" % tuple(p) for p in b["adjacent"]),
                "- UART ports: %s; analog ports: %s" % tuple(
                    ", ".join(n for n, i in sorted(b["ports"].items(), key=lambda x: int(x[0]))
                              if k in i) or "none" for k in ("uart", "analog")),
                "", "./check prints the project.yaml modules block of the build "
                "and every port the SDK would refuse (FIRMWARE lines)."]
    guide = cat.get("guide") or ""
    for h in ("project.yaml", "Rules for the `code:` block"):
        sec = _guide_section(guide, h)
        if sec:
            out += ["", "## %s (from the SDK guide)" % h, "", sec]
    out += ["", "## Modules"]
    for sid in sorted(mods):
        s = mods[sid]
        inst = INSTANCE.get(sid, sid)
        out += ["", "### %s - %s" % (sid, s["name"]),
                "CAD: %s. %s port(s), %s, class `%s`, example instance `%s`."
                % (cad_of.get(sid, "none yet"), s["size"], s["interface"],
                   s.get("class", ""), inst)]
        if s.get("description"):
            out += ["", s["description"]]
        if s.get("caution"):
            out += ["", "**CAUTION:** " + " ".join(s["caution"].split())]
        if s.get("usage"):
            out += ["", "```cpp", _named(s["usage"], inst), "```"]
        for e in s["events"]:
            out.append("- event `%s` (%s%s): %s" % (
                _named(e["key"], inst), e["value_type"],
                ", " + e["unit"] if e.get("unit") else "", _named(e["description"], inst)))
        for a in s["actions"]:
            out.append("- action `%s` (%s): %s" % (
                _named(a["key"], inst), a["value_type"], _named(a["description"], inst)))
    return "\n".join(out) + "\n"


def report(seated, ws=None, cat=None):
    """./check's FIRMWARE result for the modules a build placed:
    {"sdk", "modules", "issues", "project", "yaml"}; None without a catalog
    or without modules that carry firmware."""
    cat = cat or catalog()
    if not cat or not seated:
        return None
    entries = plan(seated, cat)
    res = {"sdk": sdk_label(cat), "modules": entries,
           "issues": issues(entries, cat=cat), "project": []}
    name = os.path.basename(os.path.normpath(ws)) if ws else "product"
    res["yaml"] = project_yaml(name, entries)
    path = os.path.join(ws, PROJECT) if ws else None
    if path and os.path.isfile(path):
        try:
            proj = read_project(path)
            res["project"] = compare(proj, entries) + lint_code(proj, cat)
            res["project_found"] = True
        except (OSError, ValueError) as exc:
            res["project"] = [str(exc)]
            res["project_found"] = True
    else:
        res["project_found"] = False
    return res


def _main(argv):
    if "--sync" in argv:
        import atech
        cat = from_sdk(atech)
        with open(SNAPSHOT, "w", encoding="utf-8") as fh:
            json.dump(cat, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print("wrote %s from atech %s (%d modules, %d boards)"
              % (SNAPSHOT, cat["sdk_version"], len(cat["modules"]), len(cat["boards"])))
        return 0
    if "--reference" in argv:
        sys.stdout.write(reference_md())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
