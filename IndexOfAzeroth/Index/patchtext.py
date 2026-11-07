# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin


class Node:
    __slots__ = ("tag", "attrs", "kids")

    def __init__(self, tag, attrs=None):
        self.tag, self.attrs, self.kids = tag, attrs or {}, []


class Cleaner(HTMLParser):
    KEEP = {"p", "ul", "ol", "li", "strong", "b", "em", "i", "blockquote", "code", "a", "h3", "h4"}
    HEAD = {"h1": "h3", "h2": "h3", "h3": "h4", "h4": "h4", "h5": "h4", "h6": "h4"}
    DROP = {"script", "style", "aside", "iframe"}

    def __init__(self, base=None):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.root = Node("root")
        self.stack = [self.root]
        self.skip = 0

    def open_node(self):
        return next(n for n in reversed(self.stack) if n is not None)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip or tag in self.DROP:
            self.skip += tag in self.DROP
            return
        if tag == "img":
            if "emoji" in (a.get("class") or "") and a.get("alt"):
                self.open_node().kids.append(a["alt"])
            return
        if tag == "br":
            self.open_node().kids.append(Node("br"))
            return
        attrs = {}
        if tag == "a":
            href = a.get("href") or ""
            if href.startswith("/") and self.base:
                href = urljoin(self.base, href)
            if "anchor" in (a.get("class") or "") or not href.startswith(("https://", "http://")):
                self.stack.append(None)
                return
            attrs = {"href": href}
        tag = self.HEAD.get(tag, tag)
        if tag not in self.KEEP:
            self.stack.append(None)
            return
        node = Node(tag, attrs)
        self.open_node().kids.append(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        if tag in self.DROP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag in ("img", "br") or len(self.stack) < 2:
            return
        self.stack.pop()

    def handle_data(self, data):
        if not self.skip:
            self.open_node().kids.append(data)



def meaningful(node):
    return [k for k in node.kids if not isinstance(k, str) or k.strip()]


def text_of(node):
    return "".join(k if isinstance(k, str) else text_of(k) for k in node.kids)


def bold(node):
    return isinstance(node, Node) and node.tag in ("strong", "b")


def leads_with_bold(li):
    parts = meaningful(li)
    return bool(parts) and bold(parts[0])


def bare_label(li):
    parts = meaningful(li)
    return len(parts) == 1 and bold(parts[0])


def repair(node):
    for k in node.kids:
        if isinstance(k, Node):
            repair(k)
    if node.tag in ("ul", "ol"):
        kids, i = node.kids, 0
        while i < len(kids):
            li = kids[i]
            if isinstance(li, Node) and li.tag == "li" and bare_label(li):
                j, points = i + 1, []
                while j < len(kids) and (isinstance(kids[j], str) and not kids[j].strip()
                                         or isinstance(kids[j], Node) and kids[j].tag == "li" and not leads_with_bold(kids[j])):
                    if isinstance(kids[j], Node):
                        points.append(kids[j])
                    j += 1
                if points:
                    sub = Node(node.tag)
                    sub.kids = points
                    li.kids.append(sub)
                    del kids[i + 1:j]
            i += 1
    for k in node.kids:
        if isinstance(k, Node) and k.tag == "p":
            parts = meaningful(k)
            if len(parts) == 1 and bold(parts[0]) and 0 < len(text_of(k).strip()) <= 80:
                k.tag, k.kids = "h4", parts[0].kids
    node.kids = [k for k in node.kids if not (isinstance(k, Node) and k.tag in ("li", "p") and not text_of(k).strip())]


def serialize(node):
    out = []
    for k in node.kids:
        if isinstance(k, str):
            out.append(html.escape(k, quote=False))
        elif k.tag == "br":
            out.append("<br>")
        elif k.tag == "a":
            out.append(f'<a href="{html.escape(k.attrs["href"])}" target="_blank" rel="noopener noreferrer">{serialize(k)}</a>')
        else:
            out.append(f"<{k.tag}>{serialize(k)}</{k.tag}>")
    return "".join(out)


def clean(cooked, base=None):
    c = Cleaner(base)
    c.feed(cooked or "")
    c.close()
    repair(c.root)
    return serialize(c.root).strip()


def plain(cooked):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cooked or ""))).strip()
