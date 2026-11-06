# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import ast
import hashlib
import re
import symtable

MARK = "LOADED_ONLY"
NAMED = "NAMED_ONLY"
DATA, PLANS, SUITES = "data", "plans", "suites"
KINDS = (DATA, PLANS, SUITES)
LOAD, MAIN = "", "__main__"
IMPORT = "import:"
AT_IMPORT = "at import:"
TAKEN = "taken:"
BY_KEY = "READ_BY_KEY"
KEY = "key:"
STORE = "store:"
MUTATORS = frozenset({"append", "extend", "insert", "update", "setdefault", "add", "pop", "popitem", "remove", "discard",
                      "clear", "sort", "reverse", "appendleft", "extendleft", "difference_update",
                      "intersection_update", "symmetric_difference_update", "__setitem__", "__delitem__"})
BEYOND = frozenset({"open", "exec", "eval", "compile", "__import__", "globals", "vars", "setattr", "delattr", "print",
                    "input", "breakpoint", "exit", "quit", "help"})


def marks(tree, mark=MARK):
    for node in tree.body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == [mark]:
            v = node.value
            if isinstance(v, (ast.Tuple, ast.List, ast.Set)) and v.elts and all(
                    isinstance(e, ast.Constant) and e.value in KINDS for e in v.elts):
                return frozenset(e.value for e in v.elts)
    return frozenset()


def file_marks(path, mark=MARK):
    if not path.endswith(".py"):
        return frozenset()
    try:
        with open(path, "rb") as f:
            return marks(ast.parse(f.read()), mark)
    except (OSError, SyntaxError, ValueError):
        return frozenset()


def by_key(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == [BY_KEY]:
            v = node.value
            if isinstance(v, ast.Tuple) and len(v.elts) in (3, 4) and all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value for e in v.elts):
                return tuple(e.value for e in v.elts)
    return None


def counts(marked, kind, own=False):
    return kind not in marked or (kind == SUITES and own)


def shape(tree):
    out = []
    for node in ast.walk(tree):
        fields = [type(node).__name__]
        for k, v in ast.iter_fields(node):
            if isinstance(v, ast.AST):
                fields.append(f"{k}*")
            elif isinstance(v, list) and v:
                fields.append(f"{k}[{','.join('*' if isinstance(i, ast.AST) else repr(i) for i in v)}]")
            elif v is not None and v != []:
                fields.append(f"{k}={v!r}")
        out.append(" ".join(fields))
    return "\n".join(out)


def digest(*trees):
    return hashlib.sha1("\n--\n".join(shape(t) for t in trees).encode()).hexdigest()


def main_guard(node):
    test = node.test if isinstance(node, ast.If) else None
    return isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__" \
        and any(isinstance(c, ast.Constant) and c.value == "__main__"
                or isinstance(c, ast.Tuple) and any(isinstance(e, ast.Constant) and e.value == "__main__" for e in c.elts)
                for c in test.comparators)


def bound(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else []
    return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}


def parse(text):
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and ast.get_docstring(node, clean=False) is not None:
            node.body = node.body[1:]
    return tree


def plain(node):
    value = getattr(node, "value", None)
    return bool(bound(node)) and not any(isinstance(n, ast.Call) for n in ast.walk(value or ast.Pass()))


def statements(tree, ours=None):
    out = []
    for node in tree.body:
        names = bound(node)
        if main_guard(node):
            kind = "main"
        elif plain(node) and not any((ours or bool)(d) for d in getattr(node, "decorator_list", ())):
            kind = "named"
        else:
            kind = "load"
        out.append((node, names, kind, hashlib.sha1(shape(node).encode()).hexdigest()))
    return out


def imports(node):
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and not node.level:
        return [node.module]
    return None


def taken(node):
    if isinstance(node, ast.Import):
        return [(a.asname or a.name.split(".")[0], a.name) for a in node.names]
    return [(a.asname or a.name, f"{node.module}:{a.name}") for a in node.names]


def _bound_inside(node):
    out, todo = set(), [node]
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
            if n is not node:
                continue
        if isinstance(n, ast.Lambda):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, ast.alias):
            out.add(n.asname or n.name.split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        todo.extend(ast.iter_child_nodes(n))
    return out


def module_names(tree):
    out = {}

    def put(name, kind):
        out[name] = kind if out.get(name, kind) == kind else "other"
    for node in tree.body:
        if main_guard(node):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            put(node.name, "def")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and plain(node):
            for n in bound(node):
                put(n, "value")
        else:
            for n in _bound_inside(node):
                put(n, "other")
    return out


def _scopes(text):
    def outer(t):
        out = {s.get_name() for s in t.get_symbols()
               if s.is_declared_global() or (s.is_global() and s.is_referenced())}
        for c in t.get_children():
            out |= outer(c)
        return out
    return {(c.get_name(), c.get_lineno()): outer(c) for c in symtable.symtable(text, "<module>", "exec").get_children()}


def _uses(node, scopes):
    inside = any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(node))
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (node.name, node.lineno) in scopes:
        at = list(node.decorator_list)
        if isinstance(node, ast.ClassDef):
            at += node.bases + [k.value for k in node.keywords]
        else:
            a = node.args
            at += a.defaults + [d for d in a.kw_defaults if d is not None] + [node.returns] + [
                x.annotation for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg] if x is not None]
        names = {n.id for x in at if x is not None for n in ast.walk(x) if isinstance(n, ast.Name)}
        return names | scopes[node.name, node.lineno], inside
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}, inside


def _reach_from(used, inside, names, uses_of):
    seen, outside, todo = set(), inside, list(used)
    while todo:
        n = todo.pop()
        kind = names.get(n)
        if kind is None:
            outside = outside or n in BEYOND
        elif n not in seen:
            seen.add(n)
            if kind == "other":
                outside = True
            for more, imported in uses_of.get(n, ()) if kind != "other" else ():
                outside = outside or imported
                todo.extend(more)
    return seen, outside


def load_reading(tree, text):
    names = module_names(tree)
    scopes = _scopes(text)
    uses_of = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or plain(node):
            for n in bound(node):
                uses_of.setdefault(n, []).append(_uses(node, scopes))
    out, held, kept, outside, fills, bare = [], {}, set(), set(), set(), set()

    statements_of = {}
    for node in tree.body:
        for n in bound(node):
            statements_of.setdefault(n, []).append(node)

    def holds(node, seen, more):
        code = [node] + [s for v in seen if names.get(v) == "def" for s in statements_of.get(v, ())]
        filled = _writes(code, names) & {v for v in seen if names.get(v) == "value"}
        for v in filled:
            held.setdefault(v, set()).update((seen | more) - {v})
        return filled
    defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for node in tree.body:
        names_bound = bound(node)
        code = digest(node)
        if main_guard(node):
            out.append((node, names_bound, "main", [(MAIN, code)]))
            continue
        loaded = imports(node)
        if loaded is not None:
            keys = [(IMPORT + m, m) for m in loaded]
            for name, what in taken(node):
                keys += [(name, what), (AT_IMPORT + name, what)]
            out.append((node, {n for n, _ in taken(node)}, "import", keys))
            continue
        decorators = getattr(node, "decorator_list", [])
        if plain(node) and not decorators:
            out.append((node, names_bound, "named", [(n, code) for n in sorted(names_bound)]))
            continue
        if decorators:
            used = {n.id for d in decorators for n in ast.walk(d) if isinstance(n, ast.Name)}
            inside = any(isinstance(n, (ast.Import, ast.ImportFrom)) for d in decorators for n in ast.walk(d))
        else:
            used, inside = _uses(node, scopes)
            used -= _bound_inside(node)
        seen, leaves = _reach_from(used, inside, names, uses_of)
        if leaves:
            outside |= seen
            out.append((node, names_bound, "load", [(LOAD, code)]))
            continue
        kept |= seen
        if decorators:
            filled = holds(node, seen, names_bound)
            fills |= {v for v in seen if names.get(v) == "def"}
            at = digest(*decorators)
            keys = [(AT_IMPORT + n, at) for n in sorted(names_bound)]
            if all(_hands_back(d, defs) for d in decorators):
                bare.update(names_bound)
                node.decorator_list = []
                own = digest(node)
                node.decorator_list = decorators
                keys += [(n, own) for n in sorted(names_bound)] + [(v, at) for v in sorted(filled)]
            else:
                keys += [(n, code) for n in sorted(names_bound)]
            out.append((node, names_bound, "kept", keys))
            continue
        touched = names_bound | holds(node, seen, names_bound)
        out.append((node, names_bound, "kept", [(k, code) for k in sorted(touched)]
                    + [(AT_IMPORT + k, code) for k in sorted(touched)]))
    return {"statements": out, "held": held, "kept": kept, "outside": outside, "fills": fills, "bare": bare}


def _writes(code, names):
    out = set()
    for node in code:
        for n in ast.walk(node):
            if isinstance(n, ast.Subscript) and not isinstance(n.ctx, ast.Load) and isinstance(n.value, ast.Name):
                out.add(n.value.id)
            elif isinstance(n, ast.AugAssign):
                target = n.target.value if isinstance(n.target, ast.Subscript) else n.target
                if isinstance(target, ast.Name):
                    out.add(target.id)
            elif isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.attr in MUTATORS:
                    out.add(f.value.id)
                if isinstance(f, ast.Name) and names.get(f.id) == "def":
                    out.update(a.id for a in n.args + [k.value for k in n.keywords] if isinstance(a, ast.Name))
    return out


def _own_returns(fn):
    out, todo = [], list(fn.body)
    while todo:
        n = todo.pop()
        if isinstance(n, ast.Return):
            out.append(n)
        elif not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            todo.extend(ast.iter_child_nodes(n))
    return out


def _gives_its_first(fn):
    params = fn.args.posonlyargs + fn.args.args
    if not params:
        return False
    first = params[0].arg
    returns = _own_returns(fn)
    return bool(returns) and all(isinstance(r.value, ast.Name) and r.value.id == first for r in returns) and not any(
        isinstance(n, ast.Name) and n.id == first and not isinstance(n.ctx, ast.Load) for n in ast.walk(fn))


def _hands_back(decorator, defs):
    if isinstance(decorator, ast.Name) and decorator.id in defs:
        return _gives_its_first(defs[decorator.id])
    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id in defs:
        outer = defs[decorator.func.id]
        inner = {n.name: n for n in outer.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        returns = _own_returns(outer)
        return bool(returns) and all(isinstance(r.value, ast.Name) and r.value.id in inner
                                     and _gives_its_first(inner[r.value.id]) for r in returns)
    return False


def keyed(text):
    return _keyed(text)[0]


def _keyed(text):
    reading = load_reading(parse(text), text)
    out = {}
    for _node, _names, _kind, keys in reading["statements"]:
        for key, code in keys:
            out.setdefault(key, []).append(code)
    return out, reading["kept"], reading["outside"]


def loaded_by(key):
    return key[len(IMPORT):] if key.startswith(IMPORT) else None


def changed_lines(rel, before, after, lines):
    try:
        a = lines(rel, before) if before is not None else {}
        b = lines(rel, after) if after is not None else {}
    except Exception:
        return None
    return {KEY + k for k in set(a) | set(b) if a.get(k) != b.get(k)}


def a_name(key):
    return key not in (LOAD, MAIN) and not key.startswith((IMPORT, AT_IMPORT, TAKEN, KEY, STORE))


def changed_names(before, after, script=False):
    try:
        if script:
            a, b = js_keyed(before), js_keyed(after)
            kept, outside = set(), set()
        else:
            (a, kept_a, out_a), (b, kept_b, out_b) = _keyed(before), _keyed(after)
            kept, outside = kept_a | kept_b, out_a | out_b
    except (SyntaxError, ValueError, RecursionError):
        return None
    out = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    for k in [k for k in out if a_name(k)]:
        if k in a and k not in b:
            out.add(TAKEN + k)
        if k in outside:
            out.add(LOAD)
        elif k in kept:
            out.add(AT_IMPORT + k)
    return out



REGEX_AFTER = frozenset({"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case", "do",
                         "else", "yield", "await"})
JS_NAMED = re.compile(r"^(?:async\s+)?function\s*\*?\s*(\w+)|^(?:const|let|var|class)\s+(\w+)")
JS_FIELD = re.compile(r"^([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)\s*=(?!=)")
JS_FUNCTION = re.compile(r"^(?:async\s+)?(?:function\b|\([^()]*\)\s*=>|[\w$]+\s*=>)")
JS_CALL = re.compile(r"[\w$)\]]\s*\(")


def js_marks(text):
    n = len(text)
    mark, tops = ["c"] * n, [True]
    depth, opened, i, last = 0, [], 0, "op"

    def lit(a, b, m):
        for k in range(a, b):
            mark[k] = m
            if text[k] == "\n":
                tops.append(False)
    while i < n:
        ch = text[i]
        if ch == "\n":
            tops.append(depth == 0 and not opened)
            i += 1
        elif ch in " \t\r\f\v":
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            lit(i, j, "x")
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                return None
            lit(i, j + 2, "x")
            i = j + 2
        elif ch in "'\"":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            if j >= n or text[j] != ch:
                return None
            lit(i, j + 1, "s")
            i, last = j + 1, "id"
        elif ch == "`" or (ch == "}" and opened and depth == opened[-1]):
            if ch == "}":
                opened.pop()
            j = i + 1
            while j < n and text[j] != "`" and not text.startswith("${", j):
                j += 2 if text[j] == "\\" else 1
            if j >= n:
                return None
            if text[j] == "`":
                lit(i, j + 1, "s")
                i, last = j + 1, "id"
            else:
                lit(i, j + 2, "s")
                opened.append(depth)
                i, last = j + 2, "op"
        elif ch == "/" and last not in ("id", ")", "]"):
            j, cls = i + 1, False
            while j < n and text[j] != "\n" and (cls or text[j] != "/"):
                if text[j] == "\\":
                    j += 1
                elif text[j] == "[":
                    cls = True
                elif text[j] == "]":
                    cls = False
                j += 1
            if j >= n or text[j] != "/":
                return None
            j += 1
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            lit(i, j, "s")
            i, last = j, "id"
        elif ch in "([{":
            depth += 1
            i, last = i + 1, "op"
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                return None
            i, last = i + 1, ch if ch != "}" else "op"
        elif ch.isalnum() or ch in "_$":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            last = "op" if text[i:j] in REGEX_AFTER else "id"
            i = j
        else:
            i, last = i + 1, "op"
    if depth or opened:
        return None
    return mark, tops


def js_statements(text):
    read = js_marks(text)
    if read is None:
        return None
    mark, tops = read
    starts, at = [], 0
    for k, line in enumerate(text.split("\n")):
        if tops[k] and line[:1] not in ("", " ", "\t", "\r", "}", ")", "]") and mark[at] != "x":
            starts.append(at)
        at += len(line) + 1
    if not starts or starts[0] != 0:
        starts.insert(0, 0)
    out = []
    for a, b in zip(starts, starts[1:] + [len(text)]):
        code, bare, space = [], [], False
        for k in range(a, b):
            ch, m = text[k], mark[k]
            if m == "x":
                continue
            if m == "c" and ch.isspace():
                space = True
                continue
            if space and code:
                code.append(" ")
                bare.append(" ")
            space = False
            code.append(ch)
            bare.append(ch if m == "c" else "")
        code, bare = "".join(code), "".join(bare)
        if not code:
            continue
        got = JS_NAMED.match(code)
        field = JS_FIELD.match(code)
        name = (got.group(1) or got.group(2)) if got else field.group(1) if field else None
        if name is None or field:
            load = True
        elif bare.startswith(("const", "let", "var")) and "=" in bare:
            init = bare.split("=", 1)[1].strip()
            load = not JS_FUNCTION.match(init) and bool(JS_CALL.search(init))
        else:
            load = False
        out.append((name, load, code))
    return out


def js_keyed(text):
    got = js_statements(text)
    if got is None:
        raise ValueError("a script left open")
    out = {}
    for name, load, code in got:
        h = hashlib.sha1(code.encode()).hexdigest()
        if name:
            out.setdefault(name, []).append(h)
        if load:
            out.setdefault(LOAD, []).append(h)
    return out
