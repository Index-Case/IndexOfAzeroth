# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import re

UNCOUNTABLE = {"bread", "blood", "cloth", "deer", "dust", "fish", "flesh", "food", "gold", "ichor", "iron", "leather",
               "meat", "moose", "mithril", "ore", "powder", "sand", "sheep", "silk", "silver", "slime", "thorium",
               "venom", "vermin", "water", "wool", "mail", "armor", "mojo", "residue", "ash", "ashes", "moss", "bile"}
IRREGULAR = {"foot": "feet", "tooth": "teeth", "mouse": "mice", "louse": "lice", "man": "men", "woman": "women"}
EXACT = {"ox": "oxen", "child": "children", "goose": "geese"}
MAN_STAYS = {"human", "shaman", "talisman", "caiman", "ottoman", "german"}
F_TO_VES = {"wolf", "elf", "dwarf", "thief", "leaf", "knife", "life", "wife", "half", "hoof", "scarf", "loaf", "shelf",
            "calf", "self"}


def plural_word(word):
    low = word.lower()
    if low in UNCOUNTABLE or not low[-1:].isalpha():
        return word
    if low in EXACT:
        return _cased(EXACT[low], word)
    for end in ("foot", "tooth", "mouse", "louse", "woman", "man"):
        if low.endswith(end) and not (end == "man" and low in MAN_STAYS):
            return word[:len(word) - len(end)] + _cased(IRREGULAR[end], word[len(word) - len(end):])
    if low in F_TO_VES or any(low.endswith(f) for f in ("wolf", "thief", "dwarf")):
        return word[:-2] + "ves" if low.endswith("fe") else word[:-1] + "ves"
    if low.endswith("s") and not low.endswith(("ss", "us", "is")):
        return word
    if low.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    if low.endswith("y") and len(low) > 1 and low[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def _cased(new, old):
    return new[0].upper() + new[1:] if old[:1].isupper() else new


def plural(name, words="", count=None):
    head, sep, tail = name.partition(" of ")
    parts = head.split()
    if not parts:
        return name
    last = parts[-1]
    forms = {last, plural_word(last), last + "s", last + "es"}
    if last.lower().endswith("y"):
        forms.add(last[:-1] + "ies")
    stem = r"\s+".join(map(re.escape, parts[:-1]))
    pattern = (stem + r"\s+" if stem else r"\b") + r"([\w']+)" + (re.escape(sep + tail) if sep else r"\b")
    if words:
        allowed = {f.lower() for f in forms}
        counted_at = rf"\b{count}\s+(?:[\w']+\s+of\s+)?" if count else None
        said = [m.group(1) for m in re.finditer(counted_at + pattern + r"(?!\s+[A-Z])", words, re.I)] if counted_at else []
        said = [g for g in said if g.lower() in allowed] or \
            [g for g in (m.group(1) for m in re.finditer(pattern, words, re.I)) if g.lower() in allowed - {last.lower()}]
        if said:
            pick = said[0]
            parts[-1] = pick[0].upper() + pick[1:] if last[:1].isupper() else pick
            return " ".join(parts) + sep + tail
    parts[-1] = plural_word(last)
    return " ".join(parts) + sep + tail
