# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
from characters import key_named
import client
from game import GameNotFound
import storedonly

TABLE = "TraitCurrencySource"


def sources(build=None):
    try:
        rows = client.rows(TABLE, build, stored=True)
    except (storedonly.NotStored, GameNotFound, OSError, ValueError):
        return {}
    out = {}
    for r in rows:
        try:
            ach, currency, amount = int(r.get("AchievementID") or 0), int(r.get("TraitCurrencyID") or 0), int(r.get("Amount") or 0)
        except ValueError:
            continue
        if ach > 0 and currency > 0:
            out[ach] = {"currency": currency, "amount": amount, "text": (r.get("Requirement_lang") or "").strip()}
    return out


def share_list(found=None):
    return sorted((sources() if found is None else found).keys())


def board(account, chars, found=None):
    if not account:
        return None
    found = sources() if found is None else found
    currency = account.get("currency")
    done, by_char, others = [], {}, 0
    for d in account.get("done") or ():
        src = found.get(d["id"]) or {}
        if src and currency and src.get("currency") != currency:
            continue
        amount = d.get("amount") or src.get("amount") or 0
        key = key_named(chars, d.get("by"))
        if key:
            by_char[key] = by_char.get(key, 0) + amount
        elif amount:
            others += amount
        done.append({"id": d["id"], "text": src.get("text") or f"Achievement {d['id']}", "amount": amount,
                     "by": d.get("by"), "key": key})
    earned = sum(d["amount"] for d in done)
    sets = {}
    for src in found.values():
        if src["currency"] == currency:
            sets.setdefault(src["text"], src["amount"])
    total = sum(sets.values()) or None
    mx = account.get("max")
    granted = max(0, mx - earned) if mx is not None and account.get("whole") else None
    return {"max": mx, "cap": account.get("cap"), "earned": earned, "granted": granted, "total": total,
            "byChar": by_char, "others": others, "done": done, "at": account.get("at")}
