# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import re

TABLES = ("Spell", "SpellName", "SpellEffect", "SpellMisc", "SpellLevels", "SpellAuraOptions", "SpellTargetRestrictions",
          "SpellCooldowns", "SpellPower", "SpellDuration", "SpellRadius", "SpellRange", "SpellCastTimes",
          "SpellDescriptionVariables", "SpellXDescriptionVariables", "Talent", "SpellReagents", "SpellTotems",
          "TotemCategory", "SpellEquippedItems", "SpellShapeshift", "SpellShapeshiftForm")
COLOUR = re.compile(r"\|[cC][0-9a-fA-F]{8}|\|[rR]")
STAT_WORDS = {"SPI": "Spirit", "AP": "Attack Power", "RAP": "Ranged Attack Power", "rap": "Ranged Attack Power",
              "SP": "Spell Power", "SPS": "Spell Power", "SPH": "Healing", "bh": "Healing", "PL": "60", "pl": "60"}
STAT_TERM = re.compile(r"\$(?:" + "|".join(STAT_WORDS) + r")(?![A-Za-z\d])")
VALUE = "smMSotdDaArRhHnuUxiveEfbqwcCgGkKp"
REGEN_AURAS, REGEN_PERIOD = {84, 85}, 5200
FUNCS = {"cond": 3, "gte": 2, "gt": 2, "lte": 2, "lt": 2, "eq": 2, "max": 2, "min": 2, "floor": 1, "ceil": 1,
         "abs": 1, "round": 1, "clamp": 3}


def number(v, default=0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return int(f) if f == int(f) else f


def fmt(v, decimals=None):
    if decimals is not None:
        return f"{v:.{decimals}f}"
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:.1f}".rstrip("0").rstrip(".")


def duration(ms):
    if ms is None or ms < 0:
        return None
    s = ms / 1000
    if s < 60:
        return f"{fmt(s)} sec"
    if s < 3600:
        return f"{fmt(round(s / 60, 1))} min"
    if s < 86400:
        h = int(s // 3600)
        return f"{h} hour" if h == 1 else f"{h} hrs"
    d = int(s // 86400)
    return f"{d} day" if d == 1 else f"{d} days"


class Gap(Exception):

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Spells:

    def __init__(self, rows):
        def first(table, key="SpellID"):
            out = {}
            for r in rows(table):
                k = int(r[key])
                if k not in out or int(r.get("DifficultyID") or 0) == 0:
                    out[k] = r
            return out

        self.text = {int(r["ID"]): r for r in rows("Spell")}
        self.name = {int(r["ID"]): r["Name_lang"] for r in rows("SpellName")}
        self.effects = {}
        for r in rows("SpellEffect"):
            sid, idx = int(r["SpellID"]), int(r["EffectIndex"])
            have = self.effects.setdefault(sid, {})
            if idx not in have or int(r["DifficultyID"]) == 0:
                have[idx] = r
        self.misc = first("SpellMisc")
        self.levels = first("SpellLevels")
        self.auras = first("SpellAuraOptions")
        self.targets = first("SpellTargetRestrictions")
        self.cooldowns = first("SpellCooldowns")
        self.power = {}
        for r in sorted(rows("SpellPower"), key=lambda r: int(r["OrderIndex"])):
            self.power.setdefault(int(r["SpellID"]), []).append(r)
        self.reagents = {int(r["SpellID"]): [(int(r[f"Reagent_{k}"]), int(r[f"ReagentCount_{k}"])) for k in range(8)
                                             if int(r[f"Reagent_{k}"] or 0) > 0] for r in rows("SpellReagents")}
        self.tools = {int(r["SpellID"]): [int(r[f"RequiredTotemCategoryID_{k}"]) for k in range(2)
                                          if int(r[f"RequiredTotemCategoryID_{k}"] or 0)] for r in rows("SpellTotems")}
        self.totems = {int(r["ID"]): r["Name_lang"] for r in rows("TotemCategory")}
        self.equipped = first("SpellEquippedItems")
        self.forms = {int(r["SpellID"]): int(r["ShapeshiftMask_0"]) & 0xFFFFFFFF for r in rows("SpellShapeshift")}
        self.form_names = {int(r["ID"]): r["Name_lang"] for r in rows("SpellShapeshiftForm")}
        self.durations = {int(r["ID"]): int(r["Duration"]) for r in rows("SpellDuration")}
        self.radius = {int(r["ID"]): number(r["Radius"]) for r in rows("SpellRadius")}
        self.ranges = {int(r["ID"]): r for r in rows("SpellRange")}
        self.casts = {int(r["ID"]): int(r["Base"]) for r in rows("SpellCastTimes")}
        self.talents = {int(r[k]) for r in rows("Talent") for k in r if (k == "SpellID" or k.startswith("SpellRank_"))
                        and int(r[k] or 0)}
        variables = {int(r["ID"]): r["Variables"] for r in rows("SpellDescriptionVariables")}
        self.variables = {}
        for r in rows("SpellXDescriptionVariables"):
            text = variables.get(int(r["SpellDescriptionVariablesID"]))
            if text:
                self.variables[int(r["SpellID"])] = parse_variables(text)

    def effect(self, sid, index):
        return (self.effects.get(sid) or {}).get(index)

    def duration_ms(self, sid):
        misc = self.misc.get(sid)
        return self.durations.get(int(misc["DurationIndex"])) if misc else None


def parse_variables(text):
    out = {}
    for m in re.finditer(r"\$(\w+)=(.*?)(?=\n\s*\$\w+=|\Z)", text, re.S):
        out[m[1]] = m[2].strip()
    return out


class Filler:

    def __init__(self, spells):
        self.spells = spells
        self.gaps = {}
        self.plain = 0


    def value(self, sid, code, index):
        sp = self.spells
        i = (index or 1) - 1
        if code in "smMSw":
            e = sp.effect(sid, i)
            if e is None:
                raise Gap(f"${code} (no effect {i + 1})")
            base = self.points(sid, e)
            var = number(e["Variance"])
            half = number(e["EffectBasePointsF"]) * var / 2
            if code == "m":
                return base - half
            if code == "M":
                return base + half
            if var and code in "sS":
                return (base - half, base + half)
            return base
        if code == "o":
            e = sp.effect(sid, i)
            if e is None:
                raise Gap("$o (no effect)")
            period, total = number(e["EffectAuraPeriod"]), sp.duration_ms(sid)
            if not period and int(e["EffectAura"]) in REGEN_AURAS:
                period = REGEN_PERIOD
            if not period or not total or total < 0:
                raise Gap("$o (no period)")
            ticks = total // period if period != REGEN_PERIOD else total / period
            base, var = self.points(sid, e), number(e["Variance"])
            if var:
                half = number(e["EffectBasePointsF"]) * var / 2
                return ((base - half) * ticks, (base + half) * ticks)
            return base * ticks
        if code == "t":
            e = sp.effect(sid, i)
            if e is None or not number(e["EffectAuraPeriod"]):
                raise Gap("$t")
            return number(e["EffectAuraPeriod"]) / 1000
        if code in "dD":
            ms = sp.duration_ms(sid)
            if ms is None or ms < 0:
                raise Gap("$d")
            return ("duration", ms)
        if code in "aA":
            def radius(r):
                return int(r["EffectRadiusIndex_0"]) or int(r["EffectRadiusIndex_1"]) if r else 0
            e = sp.effect(sid, i)
            if index is None or not radius(e):
                e = next((r for _, r in sorted((sp.effects.get(sid) or {}).items()) if radius(r)), e)
            if not radius(e):
                raise Gap("$a")
            return sp.radius.get(radius(e), 0)
        if code in "rR":
            misc = sp.misc.get(sid)
            rng = sp.ranges.get(int(misc["RangeIndex"])) if misc else None
            if not rng:
                raise Gap("$r")
            return number(rng["RangeMax_0"])
        if code in "hH":
            a = sp.auras.get(sid)
            if not a:
                raise Gap("$h")
            return number(a["ProcChance"])
        if code == "n":
            a = sp.auras.get(sid)
            if not a or not number(a["ProcCharges"]):
                raise Gap("$n")
            return number(a["ProcCharges"])
        if code in "uU":
            a = sp.auras.get(sid)
            if not a or not number(a["CumulativeAura"]):
                raise Gap("$u")
            return number(a["CumulativeAura"])
        if code == "x":
            e = sp.effect(sid, i)
            if e is None:
                raise Gap("$x")
            return number(e["EffectChainTargets"])
        if code in "iv":
            t = sp.targets.get(sid)
            if not t:
                raise Gap(f"${code}")
            return number(t["MaxTargets" if code == "i" else "MaxTargetLevel"])
        if code in "eEfbqcC":
            e = sp.effect(sid, i)
            if e is None:
                raise Gap(f"${code}")
            col = {"e": "EffectAmplitude", "E": "EffectAmplitude", "f": "EffectChainAmplitude",
                   "b": "EffectPointsPerResource", "q": "EffectMiscValue_0", "c": "EffectBonusCoefficient",
                   "C": "EffectBonusCoefficient"}[code]
            return number(e[col])
        raise Gap(f"${code}")

    def points(self, sid, e):
        base, per = number(e["EffectBasePointsF"]), number(e["EffectRealPointsPerLevel"])
        lv = self.spells.levels.get(sid)
        if per and lv and int(lv["MaxLevel"]) > int(lv["BaseLevel"]):
            base += per * (int(lv["MaxLevel"]) - int(lv["BaseLevel"]))
        return base

    def proc_cooldown(self, sid):
        a = self.spells.auras.get(sid)
        if not a or not number(a["ProcCategoryRecovery"]):
            raise Gap("$proccooldown")
        return number(a["ProcCategoryRecovery"]) / 1000


    def fill(self, sid, text=None, depth=0):
        row = self.spells.text.get(sid)
        if text is None:
            text = (row or {}).get("Description_lang") or ""
        gaps = []
        out = COLOUR.sub("", self._text(sid, text, gaps, depth))
        for g in gaps:
            self.gaps[g] = self.gaps.get(g, 0) + 1
        return out, gaps

    def _text(self, sid, text, gaps, depth):
        out, i, last = [], 0, [None]
        while i < len(text):
            c = text[i]
            if c != "$":
                out.append(c)
                i += 1
                continue
            try:
                piece, i = self._code(sid, text, i + 1, gaps, depth, last)
            except Gap as g:
                gaps.append(g.code)
                piece, i = self._skip(text, i + 1)
            if piece.startswith("[") and out and not out[-1][-1:].isspace():
                piece = " " + piece
            out.append(piece)
        return "".join(out)

    def _skip(self, text, i):
        m = re.match(r"\{[^}]*\}(?:\.\d)?|\??\w+|<\w+>", text[i:])
        n = m.end() if m else 0
        return "$" + text[i:i + n], i + n

    def _code(self, sid, text, i, gaps, depth, last):
        rest = text[i:]
        if rest.startswith("{"):
            end = matching(text, i, "{", "}")
            expr = text[i + 1:end]
            j = end + 1
            dec = re.match(r"\.(\d)", text[j:])
            if dec:
                j += 2
            if "$<" in expr or self.scaled(sid, expr) or STAT_TERM.search(expr):
                return self.spelled(sid, expr, depth), j
            v = self.evaluate(sid, expr, depth)
            last[0] = v
            return fmt(v, int(dec[1]) if dec else None) if dec else expr_number(v), j
        if rest.startswith("?"):
            return self._choice(sid, text, i, gaps, depth, last)
        if rest.startswith("@"):
            m = re.match(r"@(spelldesc|spellname|spellicon|spellaura|spelltooltip)(\d+)", rest)
            if not m:
                raise Gap("$@")
            other = int(m[2])
            j = i + m.end()
            if m[1] == "spellicon":
                return "", j
            if m[1] == "spellname":
                return self.spells.name.get(other, ""), j
            if depth > 3:
                raise Gap("$@ (too deep)")
            field = "AuraDescription_lang" if m[1] == "spellaura" else "Description_lang"
            sub = (self.spells.text.get(other) or {}).get(field) or ""
            return self._text(other, sub, gaps, depth + 1), j
        if rest[:1] in "/*":
            m = re.match(r"([/*])(\d+(?:\.\d+)?);(\d*)([a-zA-Z])(\d?)", rest)
            if not m:
                raise Gap(f"${rest[:1]}")
            v = self.value(int(m[3]) if m[3] else sid, m[4], int(m[5]) if m[5] else None)
            k = float(m[2])
            v = tuple(x / k if m[1] == "/" else x * k for x in v) if isinstance(v, tuple) else (v / k if m[1] == "/" else v * k)
            last[0] = v
            return self.show(v), i + m.end()
        if rest.startswith("<"):
            m = re.match(r"<(\w+)>", rest)
            if not m:
                raise Gap("$<")
            v = self.variable(sid, m[1], depth)
            last[0] = v
            return fmt(round_half(v)), i + m.end()
        m = re.match(r"([lL])([^:;]*):([^;]*);", rest)
        if m:
            n = last[0]
            n = n[1] if isinstance(n, tuple) else n
            word = m[2] if n is not None and abs(n) == 1 else m[3]
            return word, i + m.end()
        m = re.match(r"([gG])([^:;]*):([^;]*);", rest)
        if m:
            return m[2], i + m.end()
        m = re.match(r"proccooldown", rest)
        if m:
            v = self.proc_cooldown(sid)
            last[0] = v
            return fmt(v), i + m.end()
        m = re.match(r"(\d*)([a-zA-Z])(\d?)", rest)
        if m and m[2] in VALUE and not re.match(r"[a-zA-Z]", rest[m.end():m.end() + 1] if not m[3] else ""):
            other = int(m[1]) if m[1] else sid
            v = self.value(other, m[2], int(m[3]) if m[3] else None)
            last[0] = v
            if m[2] in "aArRt" and not isinstance(v, tuple):
                return fmt(abs(v)), i + m.end()
            return self.show(v), i + m.end()
        m = re.match(r"[a-zA-Z]+", rest)
        raise Gap("$" + (m[0] if m else rest[:1]))

    def show(self, v):
        if isinstance(v, tuple) and v and v[0] == "duration":
            return duration(v[1])
        if isinstance(v, tuple):
            lo, hi = (abs(round_half(x)) for x in v)
            return str(lo) if lo == hi else f"{lo} to {hi}"
        return str(abs(round_half(v)))

    def _choice(self, sid, text, i, gaps, depth, last):
        j = i
        branches, conds = [], []
        while j < len(text) and text[j] == "?":
            k = text.find("[", j)
            if k < 0:
                raise Gap("$?")
            conds.append(text[j + 1:k])
            end = matching(text, k, "[", "]")
            branches.append(text[k + 1:end])
            j = end + 1
        if j < len(text) and text[j] == "[":
            end = matching(text, j, "[", "]")
            branches.append(text[j + 1:end])
            j = end + 1
        else:
            branches.append("")
        names = [self.spells.name.get(int(m[1])) if m and int(m[1]) in self.spells.talents else None
                 for m in (re.fullmatch(r"\$?[asp](\d+)", c.strip()) for c in conds)]
        if names and all(names) and not self.plain:
            said = [f"{n}: {self._text(sid, b, gaps, depth).strip()}" for n, b in zip(names, branches)]
            rest = self._text(sid, branches[-1], gaps, depth).strip()
            return "[" + " / ".join(said + ([rest] if rest else [])) + "]", j
        return self._text(sid, branches[-1], gaps, depth), j

    def scaled(self, sid, expr):
        for m in re.finditer(r"\$(\d*)([smMoSw])(\d)", expr):
            e = self.spells.effect(int(m[1]) if m[1] else sid, int(m[3]) - 1)
            if e is not None and number(e["EffectRealPointsPerLevel"]):
                return True
        return False

    def spelled(self, sid, expr, depth):
        stats = []
        text = self._spelled_text(sid, expr, depth, stats)
        return f"[{text}]" if stats else f"({text})"

    def _spelled_text(self, sid, expr, depth, stats):
        if depth > 6:
            raise Gap("${} (too deep)")

        def term(m):
            if m[0].startswith("$<"):
                name = m[0][2:-1]
                held = (self.spells.variables.get(sid) or {}).get(name)
                if held is None:
                    return "1"
                if STAT_TERM.search(held):
                    inner = held[2:-1] if held.startswith("${") and held.endswith("}") else held
                    return "(" + self._spelled_text(sid, inner, depth + 1, stats) + ")"
                return expr_number(self.variable(sid, name, depth))
            if m[2] in STAT_WORDS and not m[1] and not m[3]:
                stats.append(m[2])
                return STAT_WORDS[m[2]]
            if len(m[2]) > 1:
                raise Gap(f"${m[2]}")
            v = self.value(int(m[1]) if m[1] else sid, m[2], int(m[3]) if m[3] else None)
            if isinstance(v, tuple) and v and v[0] == "duration":
                v = v[1] / 1000
            elif isinstance(v, tuple):
                v = v[0]
            return expr_number(v)

        text = re.sub(r"\$<\w+>|\$(\d*)([a-zA-Z]+)(\d*)", term, expr.replace("$*", "*"))
        text = re.sub(r"\s*([*/+])\s*", r" \1 ", text)
        text = re.sub(r"(?<=[\d)A-Za-z])\s*-\s*(?=[\d(A-Za-z])", " - ", text)
        while True:
            bare = re.sub(r"\((\d+(?:\.\d+)?)\)", r"\1", text)
            if bare == text:
                break
            text = bare
        return text.strip()

    def variable(self, sid, name, depth):
        expr = (self.spells.variables.get(sid) or {}).get(name)
        if expr is None:
            raise Gap(f"$<{name}>")
        if depth > 4:
            raise Gap("$< (too deep)")
        gaps = []
        self.plain += 1
        try:
            text = self._text(sid, expr, gaps, depth + 1).strip()
        finally:
            self.plain -= 1
        if gaps:
            raise Gap(gaps[0])
        try:
            return float(text)
        except ValueError:
            return self.evaluate(sid, text, depth + 1)

    def evaluate(self, sid, expr, depth=0):
        def sub(m):
            if m[0].startswith("$<"):
                return repr(float(self.variable(sid, m[0][2:-1], depth)))
            spell, letters, idx = m[1], m[2], m[3]
            if len(letters) > 1:
                if m.end() < len(m.string) and m.string[m.end()] == "(" and letters in FUNCS and not idx:
                    return f"_{letters}"
                if letters == "proccooldown":
                    return repr(float(self.proc_cooldown(sid)))
                raise Gap(f"${letters}")
            v = self.value(int(spell) if spell else sid, letters, int(idx) if idx else None)
            if isinstance(v, tuple) and v and v[0] == "duration":
                v = v[1] / 1000
            elif isinstance(v, tuple):
                v = v[0]
            return repr(float(v))

        clean = re.sub(r"\$<\w+>|\$(\d*)([a-zA-Z]+)(\d*)", sub, expr.replace("$*", "*"))
        clean = re.sub(r"(?<![_a-z])(cond|gte|gt|lte|lt|eq|max|min|floor|ceil|abs|round|clamp)\(", r"_\1(", clean)
        if re.search(r"[^\d\s.+\-*/(),_a-z]", clean) or re.search(r"[a-z]", re.sub(r"_[a-z]+\(", "(", clean)):
            raise Gap("${} (unread)")
        try:
            return float(eval(clean, {"__builtins__": {}}, SAFE))
        except (ZeroDivisionError, SyntaxError, TypeError, ValueError, NameError):
            raise Gap("${} (unread)")


def expr_number(v):
    return f"{abs(v):.4f}".rstrip("0").rstrip(".")


def round_half(v):
    return int(math.floor(abs(v) + 0.5)) * (1 if v >= 0 else -1)


SAFE = {"_cond": lambda c, a, b: a if c else b, "_gte": lambda a, b: a >= b, "_gt": lambda a, b: a > b,
        "_lte": lambda a, b: a <= b, "_lt": lambda a, b: a < b, "_eq": lambda a, b: a == b, "_max": max, "_min": min,
        "_floor": math.floor, "_ceil": math.ceil, "_abs": abs, "_round": round_half,
        "_clamp": lambda v, lo, hi: max(lo, min(hi, v))}


def matching(text, i, open_, close):
    depth = 0
    for j in range(i, len(text)):
        if text[j] == open_:
            depth += 1
        elif text[j] == close:
            depth -= 1
            if depth == 0:
                return j
    raise Gap(f"${open_} (unclosed)")
