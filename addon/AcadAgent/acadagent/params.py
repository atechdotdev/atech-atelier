"""params - the dimensions at the top of model.py, for hand edits (R700).

The agent writes model.py with "one parameter block at the top that holds
every dimension" (build.py's prompt). This module reads those numbers out
of the script and writes changed ones back, touching only the number's own
characters: the layout, the comments and the rest of the script stay byte
for byte, so the agent keeps editing the same design.

    read(source)              [Param] in script order
    write(source, changes)    the script with {name: value} put in
    record(ws, before, after) remember what the user changed (HAND_FILE)
    brief_lines(ws, source)   plain lines for the agent's next brief

A parameter is a module-level name bound exactly once, by a plain number
(60, 2.5, -3) or a tuple unpack of numbers (L, W, H = 60.0, 40.0, 25.0).
A name bound again (n = 0 ... n += 1, a for loop) is a variable, not a
dimension, and is left out. Booleans are left out too.

Pure Python: no FreeCAD, no Qt.
"""
import ast
import io
import json
import os
import re
import tokenize

#: In the chat workspace, beside model.py: the user's hand-set values.
HAND_FILE = "hand_params.json"

_DEG = re.compile(r"\b(deg|degrees?|angle|tilt|rot\w*)\b|°", re.I)


class Param(object):
    """One number in the parameter block."""

    __slots__ = ("name", "value", "is_int", "line", "col", "end_col",
                 "comment", "unit", "section")

    def __init__(self, name, value, is_int, line, col, end_col, comment="",
                 section=""):
        self.name = name
        self.value = value
        self.is_int = is_int
        self.line = line            # 1-based
        self.col = col              # character offsets of the literal
        self.end_col = end_col
        self.comment = comment
        self.section = section
        self.unit = unit_for(name, comment, is_int)

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    def __repr__(self):
        return "Param(%s=%r)" % (self.name, self.value)


def unit_for(name, comment, is_int):
    """"deg" for an angle, "" for a count, else "mm" (model.py is in
    millimetres and degrees)."""
    text = "%s %s" % (name, comment)
    if _DEG.search(text) or re.search(r"(^|_)(ANG|ANGLE|DEG)($|_)", name, re.I):
        return "deg"
    if is_int and not re.search(r"\bmm\b", comment):
        return ""                   # 24 teeth, 3 knuckles: a count
    return "mm"


def _number(node):
    """(value, is_int) of a numeric literal node (with an optional sign),
    else None."""
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(node.op, ast.USub) else 1
        node = node.operand
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return sign * node.value, isinstance(node.value, int)
    return None


def _bound_names(stmt):
    """Every module-level name `stmt` binds (assignments, loops, imports,
    defs, with ... as), for the "bound exactly once" rule."""
    out = []

    def targets(t):
        if isinstance(t, ast.Name):
            out.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                targets(e)
        elif isinstance(t, ast.Starred):
            targets(t.value)

    if isinstance(stmt, ast.Assign):
        for t in stmt.targets:
            targets(t)
    elif isinstance(stmt, (ast.AugAssign, ast.AnnAssign)):
        targets(stmt.target)
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        targets(stmt.target)
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        for it in stmt.items:
            if it.optional_vars is not None:
                targets(it.optional_vars)
    elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
        for a in stmt.names:
            out.append((a.asname or a.name).split(".")[0])
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        out.append(stmt.name)
    # Bindings inside for / while / if / with / try blocks at module level
    # are module-level too (a def's or a class's are not).
    for field in ("body", "orelse", "finalbody", "handlers"):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            break
        for sub in getattr(stmt, field, None) or ():
            if isinstance(sub, ast.ExceptHandler):
                if sub.name:
                    out.append(sub.name)
                for s in sub.body:
                    out += _bound_names(s)
            elif isinstance(sub, ast.stmt):
                out += _bound_names(sub)
    # A walrus anywhere binds too.
    for n in ast.walk(stmt):
        if isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name):
            out.append(n.target.id)
    return out


def _comments(source):
    """{line: text} of every comment, and the set of lines that hold only
    a comment."""
    found, alone = {}, set()
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return found, alone
    code_lines = set()
    for t in toks:
        if t.type == tokenize.COMMENT:
            found[t.start[0]] = t.string.lstrip("#").strip()
        elif t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                            tokenize.DEDENT, tokenize.ENCODING,
                            tokenize.ENDMARKER):
            code_lines.add(t.start[0])
    alone = {ln for ln in found if ln not in code_lines}
    return found, alone


def _char_col(line_text, byte_col):
    """ast's UTF-8 byte column as a character column."""
    return len(line_text.encode("utf-8")[:byte_col].decode("utf-8", "replace"))


def read(source):
    """[Param] for every dimension in `source`, in script order. A script
    that does not parse has none."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    lines = source.splitlines()
    counts = {}
    for stmt in tree.body:
        for n in _bound_names(stmt):
            counts[n] = counts.get(n, 0) + 1
    comments, alone = _comments(source)
    out = []
    section = ""
    last_line = 0
    for stmt in tree.body:
        # A comment line between statements that stands on its own heads
        # the numbers under it ("# --- wheels ---").
        # A longer block of comment lines is prose (the file's own
        # description, a note on a trap): it ends the section, names none.
        heads = [ln for ln in range(last_line + 1, stmt.lineno) if ln in alone]
        if heads:
            block = [heads[-1]]
            while block[0] - 1 in alone and block[0] - 1 > last_line:
                block.insert(0, block[0] - 1)
            head = comments[block[-1]].strip("-=#: ").strip()
            section = head if len(block) == 1 and 0 < len(head) <= 48 else ""
        last_line = getattr(stmt, "end_lineno", stmt.lineno)
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        tgt, val = stmt.targets[0], stmt.value
        pairs = []
        if isinstance(tgt, ast.Name):
            pairs = [(tgt, val)]
        elif isinstance(tgt, ast.Tuple) and isinstance(val, ast.Tuple) \
                and len(tgt.elts) == len(val.elts) \
                and all(isinstance(e, ast.Name) for e in tgt.elts):
            pairs = list(zip(tgt.elts, val.elts))
        note = comments.get(stmt.lineno, "")
        for name_node, v in pairs:
            num = _number(v)
            if num is None or counts.get(name_node.id) != 1:
                continue
            if v.lineno != v.end_lineno:
                continue
            text = lines[v.lineno - 1]
            out.append(Param(name_node.id, num[0], num[1], v.lineno,
                             _char_col(text, v.col_offset),
                             _char_col(text, v.end_col_offset),
                             comment=note, section=section))
    return out


def fmt(value, is_int):
    """A number as it goes into the script: 3 for a count, 60.0 / 2.5 /
    0.25 for a size (never 1e-05, never 59.99999999)."""
    if is_int:
        return str(int(round(value)))
    s = ("%.4f" % float(value)).rstrip("0")
    if s.endswith("."):
        s += "0"
    if s in ("-0.0",):
        s = "0.0"
    return s


def edits_on_line(edits, line):
    return sum(1 for e in edits if e[0] == line)


def write(source, changes):
    """`source` with each {name: value} of `changes` put into its literal.
    Names that are not parameters are ignored. Raises ValueError when the
    result would not parse (it always should)."""
    by_name = {p.name: p for p in read(source)}
    edits = []
    for name, value in changes.items():
        p = by_name.get(name)
        if p is None:
            continue
        new = fmt(value, p.is_int)
        if float(new) == float(p.value):
            continue
        edits.append((p.line, p.col, p.end_col, new))
    if not edits:
        return source
    lines = source.splitlines(True)
    for line, col, end, new in sorted(edits, reverse=True):
        t = lines[line - 1]
        rest = t[end:]
        # Keep a trailing comment in its column: pad or take up the
        # spaces before it (one space always stays).
        m = re.match(r"( {2,})#", rest)
        if m and edits_on_line(edits, line) == 1:
            pad = len(m.group(1)) - (len(new) - (end - col))
            rest = " " * max(1, pad) + rest[len(m.group(1)):]
        lines[line - 1] = t[:col] + new + rest
    out = "".join(lines)
    try:
        ast.parse(out)
    except SyntaxError as exc:
        raise ValueError("the edited script does not parse: %s" % exc)
    return out


# -------------------------------------------------------- the agent's side
def _hand_path(ws):
    return os.path.join(ws, HAND_FILE)


def load_hand(ws):
    try:
        with open(_hand_path(ws), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record(ws, before, after):
    """Remember that the user set these values by hand. `before` and
    `after` are {name: value}; a name put back to the agent's own value is
    forgotten. Returns the record."""
    data = load_hand(ws)
    for name, new in after.items():
        old = before.get(name)
        if old is None:
            continue
        rec = data.get(name) or {"was": old}
        if float(new) == float(rec["was"]):
            data.pop(name, None)
            continue
        rec["now"] = new
        data[name] = rec
    try:
        with open(_hand_path(ws), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
    except OSError:
        pass
    return data


def brief_lines(ws, source=None):
    """The hand-set values still in model.py, as lines for the agent's
    brief ([] when there are none). A value the agent has changed since is
    no longer the user's, and is left out."""
    data = load_hand(ws)
    if not data:
        return []
    if source is None:
        try:
            with open(os.path.join(ws, "model.py"), encoding="utf-8") as fh:
                source = fh.read()
        except OSError:
            return []
    cur = {p.name: p for p in read(source)}
    rows = []
    for name in sorted(data):
        rec, p = data[name], cur.get(name)
        if p is None or "now" not in rec or float(p.value) != float(rec["now"]):
            continue
        rows.append("- %s = %s (was %s)" % (name, fmt(p.value, p.is_int),
                                            fmt(rec["was"], p.is_int)))
    if not rows:
        return []
    return ["The user set these model.py parameters by hand. Keep their "
            "values; if intent.json disagrees, change intent.json to "
            "match them:"] + rows
