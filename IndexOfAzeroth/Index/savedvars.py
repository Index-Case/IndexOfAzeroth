# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import re

import gamefiles

__all__ = ["SavedVariablesError", "parse", "read"]


class SavedVariablesError(ValueError):
    pass


_TOKEN = re.compile(r"""
    (?P<space>\s+|--\[(?P<eq>=*)\[.*?\](?P=eq)\]|--[^\n]*)
  | (?P<string>"(?:[^"\\\n]|\\.|\\\n)*"|'(?:[^'\\\n]|\\.|\\\n)*')
  | (?P<long>\[(?P<leq>=*)\[.*?\](?P=leq)\])
  | (?P<number>-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?))
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>[{}\[\]=,;])
""", re.VERBOSE | re.DOTALL)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\\": "\\", '"': '"',
            "'": "'", "\n": "\n"}


def _unescape(body):
    out, i = bytearray(), 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            out += c.encode("utf-8")
            i += 1
            continue
        nxt = body[i + 1]
        if nxt.isdigit():
            digits = re.match(r"\d{1,3}", body[i + 1:]).group()
            out.append(int(digits) & 255)
            i += 1 + len(digits)
        else:
            out += _ESCAPES.get(nxt, nxt).encode("utf-8")
            i += 2
    return out.decode("utf-8", errors="replace")


def _tokens(text):
    at = 0
    while at < len(text):
        m = _TOKEN.match(text, at)
        if not m:
            raise SavedVariablesError(f"can't read {text[at:at + 20]!r} at {at}")
        at = m.end()
        kind = m.lastgroup
        if kind == "space":
            continue
        value = m.group()
        if kind == "string":
            value = _unescape(value[1:-1])
        elif kind == "long":
            value = value[len(m.group("leq")) + 2:-(len(m.group("leq")) + 2)]
            kind = "string"
        elif kind == "number":
            value = _number(value)
        elif kind == "name" and value in ("true", "false", "nil"):
            kind, value = "value", {"true": True, "false": False, "nil": None}[value]
        yield kind, value
    yield "end", None


def _number(s):
    low = s.lower().lstrip("-")
    if low.startswith("0x"):
        v = int(low, 16)
    elif re.fullmatch(r"\d+", low):
        v = int(low)
    else:
        v = float(low)
    return -v if s.startswith("-") else v


class _Parser:
    def __init__(self, text):
        self.tokens = _tokens(text)
        self.kind, self.value = next(self.tokens)

    def advance(self):
        self.kind, self.value = next(self.tokens)

    def expect(self, punct):
        if self.kind != "punct" or self.value != punct:
            raise SavedVariablesError(f"expected {punct!r}, found {self.value!r}")
        self.advance()

    def value_(self):
        kind, value = self.kind, self.value
        if kind in ("string", "number", "value"):
            self.advance()
            return value
        if kind == "punct" and value == "{":
            return self.table()
        raise SavedVariablesError(f"expected a value, found {value!r}")

    def table(self):
        self.expect("{")
        pairs, listed = {}, 0
        while not (self.kind == "punct" and self.value == "}"):
            if self.kind == "punct" and self.value == "[":
                self.advance()
                key = self.value_()
                self.expect("]")
                self.expect("=")
                pairs[key] = self.value_()
            elif self.kind == "name":
                key = self.value
                self.advance()
                self.expect("=")
                pairs[key] = self.value_()
            else:
                listed += 1
                pairs[listed] = self.value_()
            if self.kind == "punct" and self.value in (",", ";"):
                self.advance()
        self.advance()
        pairs = {k: v for k, v in pairs.items() if v is not None}
        if pairs and all(isinstance(k, int) and not isinstance(k, bool) for k in pairs) \
                and sorted(pairs) == list(range(1, len(pairs) + 1)):
            return [pairs[k] for k in range(1, len(pairs) + 1)]
        return pairs

    def file(self):
        out = {}
        while self.kind != "end":
            if self.kind != "name":
                raise SavedVariablesError(f"expected a variable's name, found {self.value!r}")
            name = self.value
            self.advance()
            self.expect("=")
            out[name] = self.value_()
            if self.kind == "punct" and self.value == ";":
                self.advance()
        return out


def parse(text):
    return _Parser(text.lstrip("\ufeff")).file()


def read(path):
    try:
        data = gamefiles.read_part(path)
    except FileNotFoundError:
        return {}
    return parse(data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n"))
