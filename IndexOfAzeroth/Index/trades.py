# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import collections
import itertools
import math
import random
import threading
import time

from auction import house_key, house_of_key, in_house
from ledger import AUCTION, CANCEL, LISTED, MAIL, MAILED, NOTICE, OWNED, POST, TAKE
from protocol import item_key

GRID = tuple((i + 0.5) / 20 for i in range(20))
EXACT_MOST = 7
DRAWS = 4000
SEED = 1613
MAIL_SAME = 300
SLACK = 5
LIST_LAG = 60
EXPIRE_NEAR = 900
NAME_BYTES = 48
POST_NEAR = 60

NOTICE_WHAT = {1: "sold", 2: "expired", 3: "won", 4: "outbid", 5: "removed", 6: "bid"}
SURE = ("guess", "known", "invoice", "certain")


def name_key(s):
    if not s:
        return None
    if s.endswith(")") and " (" in s and s.rsplit(" (", 1)[1][:-1].isdigit():
        s = s.rsplit(" (", 1)[0]
    return s.encode("utf-8")[:NAME_BYTES].decode("utf-8", "ignore")




class Auction(dict):

    @property
    def start(self):
        return self["posted"] if self.get("posted") is not None else self["seen"]

    @property
    def first(self):
        return min(self.start, self.get("earliest") or self.start) if self.start is not None else None

    @property
    def unit(self):
        return self["buyout"] / self["units"] if self.get("buyout") and self.get("units") else None


def auctions_of(char, entries):
    out, by_id = {}, {}
    for e in entries:
        kind = e.get("kind")
        if kind == POST:
            a = by_id.get(e.get("auction")) if e.get("auction") else None
            if a is None:
                key = f"{char}:{e['auction']}" if e.get("auction") else f"{char}:p{e['series']}:{e['seq']}"
                a = out[key] = Auction(key=key, char=char, auction=e.get("auction"), posted=e["t"], seen=e["t"], sightings=[])
                if e.get("auction"):
                    by_id[e["auction"]] = a
            a["posted"] = min(a.get("posted") or e["t"], e["t"])
            for k in ("item", "bonus", "units", "buyout", "bid", "deposit", "duration", "commodity", "name"):
                if e.get(k) is not None:
                    a[k] = e[k]
        elif kind == OWNED and e.get("auction"):
            a = by_id.get(e["auction"])
            if a is None:
                a = by_id[e["auction"]] = out[f"{char}:{e['auction']}"] = Auction(
                    key=f"{char}:{e['auction']}", char=char, auction=e["auction"], posted=None, seen=e["t"], sightings=[])
            for k in ("item", "bonus", "buyout", "bid", "commodity", "name"):
                if e.get(k) is not None and a.get(k) is None:
                    a[k] = e[k]
            a.setdefault("units", e["units"])
            a["sightings"].append((e["t"], e["units"], bool(e.get("sold")), e.get("left")))
    lengths = {}
    for a in out.values():
        for t, _, sold, left in a["sightings"]:
            if left is not None and not sold:
                a["expires"] = t + left * 60
                if a.get("posted") is not None and a.get("duration"):
                    lengths.setdefault(a["duration"], []).append(round((t + left * 60 - a["posted"]) / 3600) * 3600)
    durations = {d: sorted(v)[len(v) // 2] for d, v in lengths.items()}
    longest = max(durations.values(), default=None)
    for a in out.values():
        if a.get("expires") is None and a.get("posted") is not None and a.get("duration") in durations:
            a["expires"] = a["posted"] + durations[a["duration"]]
        a["nk"] = name_key(a.get("name"))
        if a.get("posted") is None and longest:
            a["earliest"] = min((t + left * 60 if left is not None else t) - longest for t, _, _, left in a["sightings"])
    return out, durations


def mail_key(m):
    return tuple(m.get(k) for k in ("what", "name", "money", "bid", "buyout", "deposit", "cut", "units", "item"))


def unique_mails(entries):
    out = []
    for e in sorted((e for e in entries if e.get("kind") == MAILED), key=lambda e: e["t"]):
        same = next((m for m in out if m["series"] != e["series"] and not any(s[0] == e["series"] for s in m.get("aka", ()))
                     and mail_key(m) == mail_key(e) and abs((m.get("expires") or 0) - (e.get("expires") or 0)) * 60 <= MAIL_SAME), None)
        if same:
            same.setdefault("aka", []).append((e["series"], e["seq"]))
            continue
        out.append(dict(e))
    return out



def ranks(cands, commodity):
    def price(a):
        return a.unit if a.unit is not None else math.inf
    if commodity:
        order = sorted(cands, key=lambda a: (price(a), -(a.start or 0)))
        return {a["key"]: i for i, a in enumerate(order)}
    prices = sorted({price(a) for a in cands})
    return {a["key"]: prices.index(price(a)) for a in cands}


def posterior(observations):
    logs = [0.0] * len(GRID)
    for rs, true in observations:
        for i, th in enumerate(GRID):
            logs[i] += true * math.log(th) - math.log(sum(th ** r for r in rs))
    top = max(logs)
    w = [math.exp(v - top) for v in logs]
    s = sum(w)
    return [v / s for v in w]


def joint(notices, post, again=frozenset()):
    keys = sorted({k for n in notices for k in n["cands"]})
    marg = [dict() for _ in notices]
    paths = {}

    def weights(n, th, taken):
        return {k: th ** n["ranks"][k] for k in n["cands"] if k not in taken}

    def walk(i, taken, p, th, path):
        if i == len(notices):
            paths[tuple(path)] = paths.get(tuple(path), 0.0) + p
            return
        w = weights(notices[i], th, taken)
        total = sum(w.values())
        if not total:
            marg[i][None] = marg[i].get(None, 0.0) + p
            return walk(i + 1, taken, p, th, path + [None])
        for k in sorted(w):
            q = p * w[k] / total
            marg[i][k] = marg[i].get(k, 0.0) + q
            walk(i + 1, taken if k in again else taken | {k}, q, th, path + [k])

    if len(keys) <= EXACT_MOST:
        for th, pt in zip(GRID, post):
            if pt > 1e-12:
                walk(0, frozenset(), pt, th, [])
    else:
        rng = random.Random(SEED)
        cum = list(itertools.accumulate(post))
        for _ in range(DRAWS):
            th = GRID[min(len(GRID) - 1, bisect.bisect_left(cum, rng.random() * cum[-1]))]
            taken, path = set(), []
            for i, n in enumerate(notices):
                w = weights(n, th, taken)
                pick, total = None, sum(w.values())
                if total:
                    r, acc = rng.random() * total, 0.0
                    for k in sorted(w):
                        acc += w[k]
                        pick = k
                        if r <= acc:
                            break
                    if pick not in again:
                        taken.add(pick)
                marg[i][pick] = marg[i].get(pick, 0.0) + 1.0 / DRAWS
                path.append(pick)
            paths[tuple(path)] = paths.get(tuple(path), 0.0) + 1.0 / DRAWS
    best = max(paths.items(), key=lambda kv: kv[1])[0] if paths else tuple(None for _ in notices)
    return marg, list(best)



class Trades:

    def __init__(self, ledger, chars, now=time.time, vendor=None):
        self.ledger, self.chars, self.now = ledger, chars, now
        self.vendor = vendor or (lambda item: None)
        self.lock = threading.Lock()
        self.kept = {}

    def houses(self):
        return sorted({house_key(c.get("realm"), c.get("faction")) for c in (self.chars() or {}).values()})

    def view(self, house):
        house = house_of_key(house)
        chars = {k: c for k, c in (self.chars() or {}).items() if in_house(c.get("realm"), c.get("faction"), house)}
        stamp = (self.ledger.version, tuple(sorted(chars)))
        with self.lock:
            kept = self.kept.get(house)
            if kept and kept[0] == stamp:
                return kept[1]
        got = self.work(house, chars)
        with self.lock:
            self.kept[house] = (stamp, got)
        return got

    def work(self, house, chars):
        now = self.now()
        per = {key: settle(key, self.ledger.entries(key)) for key in chars}
        observations = {"item": [], "commodity": []}
        for got in per.values():
            for kind, obs in got["observed"].items():
                observations[kind] += obs
        post = {kind: posterior(obs) for kind, obs in observations.items()}
        for got in per.values():
            guess(got, post, now)
        out = {"house": house, "now": now, "characters": [{"key": k, "name": c.get("name")} for k, c in sorted(chars.items())],
               "auctions": [], "notices": [], "sales": [], "bids": [], "deposits": {}, "saleMoney": {}}
        for key, got in per.items():
            out["auctions"] += [row(a) for a in got["auctions"].values()]
            out["notices"] += got["notices"]
            out["sales"] += got["sales"]
            out["bids"] += got["bids"]
            out["deposits"].update(got["deposits"])
            out["saleMoney"].update(got["saleMoney"])
        out["auctions"].sort(key=lambda r: r["start"] or 0)
        out["notices"].sort(key=lambda n: n["t"])
        out["rules"] = rules_read(per, self.vendor)
        out["theta"] = {kind: {"n": len(obs), "cheapest2": round(sum(p / (1 + th) for p, th in zip(post[kind], GRID)), 4)}
                        for kind, obs in observations.items()}
        out["items"] = summaries(out["auctions"])
        return out


def feasible(a, t, cancels, lists):
    if a.start is None or a.first > t + SLACK:
        return False
    c = cancels.get(a.get("auction"))
    if c is not None and c < t - SLACK:
        return False
    if a.get("expires") is not None and a["expires"] < t - SLACK:
        return False
    if a.get("auction"):
        for lt, ids in lists:
            if a.start + LIST_LAG < lt < t - SLACK and a["auction"] not in ids:
                return False
            if lt > t + SLACK and a["auction"] in ids and not a.get("commodity"):
                return False
    for st, units, sold, _ in a["sightings"]:
        if st > t + SLACK and not sold and units >= (a.get("units") or 0) and not a.get("commodity"):
            return False
    return True


def mark_sold(a, how, t, units=None):
    if a.get("commodity") and units:
        a["soldUnits"] = min(a.get("units") or 0, a["soldUnits"] + units)
    else:
        a["soldUnits"] = a.get("units") or 0
    a["outcome"] = "sold" if a["soldUnits"] >= (a.get("units") or 0) else "partly"
    if a.get("sure") is None or SURE.index(how) > SURE.index(a["sure"]):
        a["sure"] = how
    a["evidence"] = min(a.get("evidence") or t, t)


def settle(char, entries):
    auctions, durations = auctions_of(char, entries)
    cancels = {e["auction"]: e["t"] for e in entries if e.get("kind") == CANCEL}
    merged = {}
    for e in entries:
        if e.get("kind") == LISTED:
            merged.setdefault(e["t"], set()).update(e.get("ids") or ())
    lists = sorted(merged.items())
    mails = unique_mails(entries)
    taken = {}
    for e in entries:
        if "kind" not in e and e.get("cause") == MAIL and e.get("sub") == 1 and e.get("id2") is not None:
            taken[(e["series"], e["id2"])] = (e["d"], e["t"], e["series"], e["seq"])
    items_taken = {(e["series"], e["mail"]) for e in entries if e.get("kind") == TAKE and e.get("mail") is not None}
    for a in auctions.values():
        a.update(outcome="open", sure=None, soldUnits=0, history=[("posted" if a.get("posted") is not None else "seen", a.start)])
        for t, _, sold, _ in a["sightings"]:
            a["history"].append(("sold" if sold else "listed", t))
        if a.get("auction") in cancels:
            a.update(outcome="cancelled", sure="certain", ended=cancels[a["auction"]])
            a["history"].append(("cancelled", cancels[a["auction"]]))
    by_id = {a["auction"]: a for a in auctions.values() if a.get("auction")}
    for a in auctions.values():
        for t, _, sold, _ in a["sightings"]:
            if sold and a["outcome"] in ("open", "partly"):
                mark_sold(a, "known", t)
    notices = []
    for e in sorted((e for e in entries if e.get("kind") == NOTICE), key=lambda e: e["t"]):
        n = {"t": e["t"], "char": char, "what": NOTICE_WHAT.get(e.get("what"), "sold"), "name": e.get("name"),
             "nk": name_key(e.get("name")), "from": e.get("from"), "auction": None, "sure": None, "candidates": []}
        a = by_id.get(e.get("auction")) if e.get("auction") else None
        if a is not None:
            n.update(auction=a["key"], sure="known")
            if n["what"] == "sold":
                mark_sold(a, "known", e["t"])
                a.update(soldAt=e["t"], notice=len(notices))
            elif n["what"] in ("expired", "removed") and a["outcome"] == "open":
                a.update(outcome=n["what"], sure="known", ended=e["t"], noticeEnd=len(notices))
        notices.append(n)
    sales, finals = [], {}
    for m in sorted((m for m in mails if m.get("what") in (1, 2)), key=lambda m: m["t"]):
        if m.get("what") == 1:
            twin = next((p for p in sales if p.get("what") == 2 and id(p) not in finals and name_key(p.get("name")) == name_key(m.get("name"))
                         and p.get("units") == m.get("units") and p.get("buyout") == m.get("buyout") and p.get("bid") == m.get("bid")), None)
            if twin is not None:
                finals[id(twin)] = m
                continue
        sales.append(m)
    unmatched, sale_money = [], {}
    for m in sales:
        final = finals.get(id(m), m if m.get("what") == 1 else None)
        money = None
        if final is not None:
            for s in [(final["series"], final["seq"])] + list(final.get("aka", ())):
                money = money or taken.get(s)
        sure = "certain" if money else "invoice"
        a = match_sale(m, auctions.values())
        if a is None:
            unmatched.append({"t": m["t"], "char": char, "name": m.get("name"), "units": m.get("units"),
                              "buyout": m.get("buyout"), "bid": m.get("bid"), "deposit": m.get("deposit"), "cut": m.get("cut"),
                              "money": money[0] if money else (final or {}).get("money"), "takenAt": money[1] if money else None,
                              "sure": sure, "pending": final is None})
            continue
        mark_sold(a, sure, m["t"], m.get("units"))
        a["invoice"] = {"seen": m["t"], "units": m.get("units"), "buyout": m.get("buyout"), "bid": m.get("bid"),
                        "deposit": m.get("deposit"), "cut": m.get("cut"), "other": m.get("other"),
                        "money": (final or {}).get("money")}
        a["history"].append(("invoice", m["t"]))
        if money:
            a["taken"], a["takenAt"] = money[0], money[1]
            a["history"].append(("taken", money[1]))
            sale_money[f"{char}|{money[2]}|{money[3]}"] = a["key"]
    for m in sorted((m for m in mails if m.get("what") in (4, 5)), key=lambda m: m["t"]):
        what = "expired" if m["what"] == 4 else "cancelled"
        a = match_return(m, auctions.values(), what)
        if a is not None:
            a.update(outcome=what, sure="certain", ended=a.get("ended") or m["t"], returned=m["t"])
            a["history"].append((f"{what} mail", m["t"]))
            if (m["series"], m["seq"]) in items_taken:
                a["history"].append(("item taken", m["t"]))
    observed = {"item": [], "commodity": []}
    pending = {}
    settled = sorted((a for a in auctions.values() if a["outcome"] in ("sold", "partly") and a.get("notice") is None),
                     key=lambda a: a.get("evidence") or 0)
    for i, n in enumerate(notices):
        if n["what"] != "sold" or n["auction"]:
            continue
        cands = [a for a in auctions.values() if a["nk"] and a["nk"] == n["nk"] and feasible(a, n["t"], cancels, lists)
                 and (a["outcome"] in ("open", "partly") or (a["outcome"] == "sold" and a.get("notice") is None
                                                             and (a.get("evidence") or 0) >= n["t"] - SLACK))]
        n["cands_all"] = cands
        hit = next((a for a in settled if a.get("notice") is None and a in cands), None)
        if hit is not None:
            hit.update(notice=i, soldAt=n["t"])
            n.update(auction=hit["key"], sure=hit["sure"])
            rk = ranks(cands, hit.get("commodity"))
            rs = [rk[a["key"]] for a in cands]
            if len(set(rs)) > 1:
                observed["commodity" if hit.get("commodity") else "item"].append((rs, rk[hit["key"]]))
            continue
        pending.setdefault(n["nk"], []).append(i)
    for i, n in enumerate(notices):
        if n["what"] not in ("expired", "removed") or n["auction"]:
            continue
        cands = [a for a in auctions.values() if a["nk"] and a["nk"] == n["nk"] and a.start is not None
                 and a.first <= n["t"] + SLACK and a.get("noticeEnd") is None and a["outcome"] in ("open", "expired", "removed")]
        done = [a for a in cands if a["outcome"] != "open"]
        if done:
            a = min(done, key=lambda a: abs((a.get("ended") or n["t"]) - n["t"]))
            a["noticeEnd"] = i
            n.update(auction=a["key"], sure=a["sure"])
            continue
        near = [a for a in cands if a.get("expires") is not None and abs(a["expires"] - n["t"]) <= EXPIRE_NEAR]
        n["cands_end"] = near or [a for a in cands if a.get("expires") is None]
    deposits = deposits_of(char, entries, auctions)
    return {"auctions": auctions, "notices": notices, "pending": pending, "sales": unmatched,
            "bids": bids_of(char, entries, mails), "observed": observed, "durations": durations, "mails": mails,
            "deposits": deposits, "saleMoney": sale_money}


def match_sale(m, auctions):
    nk, units, t = name_key(m.get("name")), m.get("units"), m["t"]
    fits = []
    for a in auctions:
        if a["nk"] != nk or a.start is None or a.first > t + SLACK or a["outcome"] in ("cancelled", "expired"):
            continue
        if a.get("commodity") and a.unit is not None and units and m.get("buyout"):
            if units <= (a.get("units") or 0) - a["soldUnits"] and abs(m["buyout"] / units - a.unit) < 1:
                fits.append(a)
            continue
        if a.get("invoice") is not None:
            continue
        same_buyout = a.get("buyout") is not None and m.get("buyout") == a["buyout"]
        bid_met = (m.get("bid") or 0) > 0 and a.get("bid") is not None and m["bid"] >= a["bid"]
        if (units is None or a.get("units") == units) and (same_buyout or bid_met):
            fits.append(a)
    if not fits:
        return None
    return min(fits, key=lambda a: (a["outcome"] != "sold", a.start))


def match_return(m, auctions, what):
    nk, units = name_key(m.get("name")), m.get("units")
    fits = [a for a in auctions if a["nk"] == nk and (units is None or a.get("units") == units)
            and (m.get("item") is None or a.get("item") in (None, m["item"])) and a.start is not None
            and a.first <= m["t"] + SLACK and a.get("returned") is None and a["outcome"] in ("open", "removed", what)]
    if not fits:
        return None
    return min(fits, key=lambda a: (a["outcome"] != what, abs((a.get("expires") or a.start) - m["t"]) if what == "expired" else a.start))


def deposits_of(char, entries, auctions):
    out, used = {}, set()
    deposits = [e for e in entries if "kind" not in e and e.get("cause") == AUCTION and e.get("sub") == 1]
    by_id = {e["id2"]: e for e in deposits if e.get("id2") is not None}
    for a in auctions.values():
        e = by_id.get(a.get("auction")) if a.get("auction") else None
        if e is None and a.get("posted") is not None:
            e = next((e for e in deposits if e.get("id2") is None and (e["series"], e["seq"]) not in used
                      and e.get("id") == a.get("item") and e.get("count") == a.get("units")
                      and abs(e["t"] - a["posted"]) <= POST_NEAR), None)
        if e is not None:
            used.add((e["series"], e["seq"]))
            out[a["key"]] = [char, e["series"], e["seq"]]
            a["paid"] = -e["d"]
    return out


def bids_of(char, entries, mails):
    out = []
    for e in entries:
        if "kind" in e or e.get("cause") != AUCTION or e.get("sub") not in (2, 3, 4):
            continue
        out.append({"t": e["t"], "char": char, "item": e.get("id"), "bonus": e.get("bonus"), "units": e.get("count"),
                    "paid": -e["d"], "auction": e.get("id2"), "how": {2: "buyout", 3: "bid", 4: "commodity"}[e["sub"]],
                    "outcome": "open" if e["sub"] == 3 else "bought"})
    for m in sorted(mails, key=lambda m: m["t"]):
        if m.get("what") == 6:
            b = next((b for b in out if b["how"] == "bid" and b["outcome"] == "open" and b["t"] <= m["t"] + SLACK), None)
            if b is not None:
                b.update(outcome="outbid", refund=m.get("money"))
        elif m.get("what") == 3:
            b = next((b for b in out if b["how"] == "bid" and b["outcome"] == "open" and b["t"] <= m["t"] + SLACK
                      and (b.get("item") is None or m.get("item") is None or b["item"] == m["item"])), None)
            if b is not None:
                b.update(outcome="won", name=m.get("name"))
    return out


def guess(got, post, now):
    auctions, notices = got["auctions"], got["notices"]
    for idx in got["pending"].values():
        group, again = [], set()
        for i in idx:
            cands = [a for a in notices[i].get("cands_all", []) if a["outcome"] in ("open", "partly")]
            commodity = any(a.get("commodity") for a in cands)
            again |= {a["key"] for a in cands if a.get("commodity")}
            group.append({"i": i, "cands": [a["key"] for a in cands], "ranks": ranks(cands, commodity), "commodity": commodity})
        kind = "commodity" if any(g["commodity"] for g in group) else "item"
        marg, best = joint(group, post[kind], frozenset(again))
        for g, m, pick in zip(group, marg, best):
            n = notices[g["i"]]
            n.update(sure="guess", prior=kind, auction=pick, chance=round(m.get(pick, 0.0), 4) if pick else None,
                     none=round(m.get(None, 0.0), 4),
                     candidates=sorted(({"key": k, "chance": round(p, 4)} for k, p in m.items() if k), key=lambda c: -c["chance"]))
            for k, p in m.items():
                if k:
                    auctions[k]["chanceSold"] = auctions[k].get("chanceSold", 0.0) + p
            if pick and auctions[pick]["outcome"] == "open":
                auctions[pick].update(outcome="sold", sure="guess", chance=m[pick], soldAt=n["t"], notice=g["i"])
    for n in notices:
        cands = n.pop("cands_end", None)
        if cands is not None and not n["auction"]:
            w = {a["key"]: max(0.0, 1.0 - a.get("chanceSold", 0.0)) for a in cands if a["outcome"] in ("open", "sold")}
            total = sum(w.values())
            chances = {k: v / total for k, v in w.items()} if total else {}
            n.update(sure="guess", candidates=sorted(({"key": k, "chance": round(p, 4)} for k, p in chances.items()),
                                                     key=lambda c: -c["chance"]), none=0.0 if chances else 1.0)
            if chances:
                pick = max(chances, key=lambda k: (chances[k], k))
                n.update(auction=pick, chance=round(chances[pick], 4))
                if auctions[pick]["outcome"] == "open":
                    auctions[pick].update(outcome=n["what"], sure="guess", chance=chances[pick], ended=n["t"])
        n.pop("cands_all", None)
        n.pop("nk", None)
    for a in auctions.values():
        if a["outcome"] == "open" and a.get("expires") is not None and a["expires"] < now:
            a["outcome"] = "ended"


def item_key_of(r):
    return str(item_key(r["item"], r.get("bonus") or ())) if r.get("item") else None


def row(a):
    out = {k: a.get(k) for k in ("key", "char", "auction", "item", "bonus", "name", "units", "buyout", "bid", "deposit",
                                 "paid", "duration", "commodity", "posted", "seen", "expires", "outcome", "sure", "soldAt",
                                 "ended", "taken", "takenAt", "invoice", "soldUnits")}
    out["start"], out["unit"] = a.start, a.unit
    out["itemKey"] = item_key_of(a)
    out["history"] = sorted(([w, t] for w, t in a["history"] if t is not None), key=lambda h: h[1])
    if a.get("soldAt") is not None and a.get("posted") is not None:
        out["took"] = max(0, a["soldAt"] - a["posted"])
    for k in ("chance", "chanceSold"):
        if a.get(k) is not None:
            out[k] = round(a[k], 4)
    return out


def rules_read(per, vendor):
    cuts, posts, durations = [], [], {}
    for got in per.values():
        for m in got["mails"]:
            if m.get("what") not in (1, 2) or m.get("cut") is None:
                continue
            price = (m["money"] - (m.get("deposit") or 0) + m["cut"]) if m.get("what") == 1 and m.get("money") else (
                m.get("buyout") or m.get("bid"))
            if price:
                cuts.append((m["t"], m["cut"] / price, (m["cut"] - 1) / price, (m["cut"] + 1) / price))
        for a in got["auctions"].values():
            if a.get("posted") is not None and a.get("deposit") and a.get("units") and a.get("duration"):
                posts.append((a["posted"], a["duration"], a["deposit"], a["units"], a.get("item")))
        durations.update(got["durations"])
    out = {"cut": None, "deposit": None, "least": None, "durations": durations}
    if cuts:
        cuts.sort()
        shares = [s for _, s, _, _ in cuts]
        out["cut"] = {"share": agreed_rate(cuts, "cut"), "n": len(cuts), "low": min(shares), "high": max(shares),
                      "seen": cuts[-1][0]}
    if posts:
        dep, readings = {}, collections.defaultdict(list)
        for t, d, deposit, units, item in sorted(posts):
            each = vendor(item) if item else None
            dep[d] = {"deposit": deposit, "units": units, "item": item, "seen": t, "n": dep.get(d, {}).get("n", 0) + 1}
            if each:
                readings[d].append((t, deposit / (each * units), (deposit - units) / (each * units),
                                    (deposit + units) / (each * units)))
        for d, got in dep.items():
            got["rate"] = agreed_rate(readings[d], f"deposit {d}") if readings[d] else None
        out["deposit"] = dep
        out["least"] = min(p[2] for p in posts)
    return out


_dropped = set()


def agreed_rate(readings, what):
    def meets(a, b):
        return a[2] <= b[3] and b[2] <= a[3]
    low, high, newest = -math.inf, math.inf, None
    for i in range(len(readings) - 1, -1, -1):
        r = readings[i]
        if len(readings) > 1 and not any(meets(r, o) for j, o in enumerate(readings) if j != i):
            if (what, r[0]) not in _dropped:
                _dropped.add((what, r[0]))
                from serverlog import log_note
                log_note(f"auction house {what}: a reading of {r[1]:.6g} at {r[0]:.0f} agrees with no other, left out")
            continue
        if max(low, r[2]) > min(high, r[3]):
            break
        low, high = max(low, r[2]), min(high, r[3])
        newest = r[1] if newest is None else newest
    if newest is None:
        return readings[-1][1] if readings else None
    for places in range(10):
        step = 10.0 ** -places
        first, last = math.ceil(low / step - 1e-9), math.floor(high / step + 1e-9)
        if first <= last:
            n = min(max(round(newest / step), first), last)
            return round(n * step, places)
    return newest


def resold(view):
    lots = {}
    for b in sorted(view["bids"], key=lambda b: b["t"]):
        if b.get("item") and b.get("units") and b["outcome"] in ("bought", "won"):
            lots.setdefault(b["item"], []).append([b["t"], b["units"], b["paid"] / b["units"]])
    rows = {r["key"]: r for r in view["auctions"]}
    out = {}
    for money, r in sorted(((m, rows[k]) for m, k in view["saleMoney"].items() if k in rows), key=lambda s: s[1].get("takenAt") or 0):
        units = r.get("soldUnits") or r.get("units")
        if not units or r.get("taken") is None or not r.get("item"):
            continue
        net = (r["taken"] - ((r.get("invoice") or {}).get("deposit") or 0)) / units
        loss, left = 0.0, units
        for lot in lots.get(r["item"], ()):
            if left <= 0:
                break
            if lot[1] <= 0 or lot[0] > r["start"]:
                continue
            take = min(left, lot[1])
            lot[1] -= take
            left -= take
            loss += max(0.0, lot[2] - net) * take
        if loss >= 1:
            out[money] = round(loss)
    return out



PRICE_SLACK = 1


def action_key(item, bonus, suffixed):
    if not item:
        return None
    if bonus is not None:
        return str(item_key(item, bonus))
    return None if item in suffixed else str(item)


def listing_now(view, listing, suffixed, owned=()):
    from auction import POOLED, key_item
    from goods import SOLD, matches_of, unit_price
    by_item = {}
    for k in listing:
        by_item.setdefault(key_item(k), []).append(k)
    now, copied, applied = dict(listing), set(), []

    def rows_of(k):
        if k not in copied:
            copied.add(k)
            now[k] = (now[k][0], list(now[k][1]))
        return now[k][1]

    def keys_at(item, key, t, up=None):
        keys = [key] if key in listing else by_item.get(item, [])
        return [k for k in keys if listing[k][0] < t and (up is None or listing[k][0] >= up)]

    def take(item, key, t, fits, up=None):
        hits = [(k, r) for k in keys_at(item, key, t, up) for r in now[k][1] if fits(r)]
        under = {k for k, _ in hits}
        for k, r in (hits[:1] if len(under) == 1 else hits):
            rows_of(k).remove(r)
        if hits:
            applied.append(t)
        one = next(iter(under)) if len(under) == 1 else None
        told = key or (one if one and not one.endswith(f":{POOLED}") else None)
        return told, hits[0][1][2] if len(hits) == 1 else None

    def cheaper_gone(key, t, units, paid):
        if key is None or key not in listing or listing[key][0] >= t or not units:
            return
        gone = [r for r in now[key][1] if r[2] == units and 0 < r[3] < paid - PRICE_SLACK]
        for r in gone:
            rows_of(key).remove(r)
        if gone:
            applied.append(t)

    def take_units(item, key, t, units):
        asks = sorted(((k, r) for k in keys_at(item, key, t) for r in now[k][1] if r[2] > 0 and r[3] > 0),
                      key=lambda kr: kr[1][3] / kr[1][2])
        for k, r in asks:
            if units <= 0:
                break
            got, rows = min(units, r[2]), rows_of(k)
            i = rows.index(r)
            if got == r[2]:
                del rows[i]
            else:
                rows[i] = [r[0], r[1], r[2] - got, round(r[3] / r[2] * (r[2] - got)), *r[4:]]
            units -= got
            applied.append(t)

    bought = []
    for b in sorted(view["bids"], key=lambda b: b["t"]):
        if b["how"] not in ("buyout", "commodity") or not b.get("item"):
            continue
        key, units = action_key(b["item"], b.get("bonus"), suffixed), b.get("units")
        if b["how"] == "commodity":
            if units:
                take_units(b["item"], key, b["t"], units)
        else:
            paid, told = b["paid"], key
            key, one = take(b["item"], key, b["t"], lambda r: r[3] > 0 and abs(r[3] - paid) <= PRICE_SLACK
                            and (units is None or r[2] == units))
            units = units or one
            cheaper_gone(told, b["t"], units, paid)
        bought.append({"char": b["char"], "key": key, "units": units, "t": b["t"], "paid": b["paid"]})
    cancelled, ended = [], set()
    for a in view["auctions"]:
        left = (a.get("units") or 0) - (a.get("soldUnits") or 0)
        if a["outcome"] == "cancelled" and a.get("auction"):
            ended.add(a["auction"])
        if not a.get("item") or left <= 0 or a["outcome"] != "cancelled" or a.get("ended") is None:
            continue
        key, whole, units, unit = action_key(a["item"], a.get("bonus"), suffixed), a.get("buyout"), a.get("units"), a.get("unit")
        fits = None
        if a.get("commodity") and unit:
            fits = lambda r: r[2] > 0 and abs(r[3] / r[2] - unit) <= PRICE_SLACK
        elif whole and units:
            fits = lambda r: r[2] == units and abs(r[3] - whole) <= PRICE_SLACK
        if fits and a["start"] is not None:
            key, _ = take(a["item"], key, a["ended"], fits, up=a["start"])
        cancelled.append({"char": a["char"], "key": key, "units": left, "t": a["ended"]})
    mine = {}
    for a, at, seen in owned:
        if a.get("key") and not a["flags"] & SOLD and a["id"] not in ended:
            mine.setdefault(a["key"], []).append((a, at, seen))
    yours = {}
    for key, group in mine.items():
        t, rows = now.get(key) or (None, [])
        units = {a["id"]: unit_price(a, rows) for a, _, _ in group}
        found = matches_of(rows, [(a, units[a["id"]], at) for a, at, _ in group], t) if t is not None else {}
        held = [rows[i] for i in sorted(set(found.values()))]
        for r in held:
            rows_of(key).remove(r)
        since = [[a["item"], ":".join(key.split(":")[1:]) or 0, a["q"], round(units[a["id"]] * a["q"]), 0, 0, None]
                 for a, _, seen in group if a["id"] not in found and units[a["id"]] and (t is None or seen > t)]
        if held or since:
            yours[key] = held + since
            applied.append(max(seen for _, _, seen in group))
    emptied = {k: listing[k][1] for k in copied if listing[k][1] and not now[k][1]}
    return {"listing": now, "yours": yours, "emptied": emptied, "bought": bought, "cancelled": cancelled,
            "mark": (len(applied), max(applied, default=None))}


def to_mail(acts):
    return [(a["char"], a["key"], a["units"], a["t"]) for a in acts["bought"] + acts["cancelled"] if a["key"] and a["units"]]


def paid_for(view, acts, held):
    lots = {}
    for b in acts["bought"]:
        if b["key"] and b["units"]:
            lots.setdefault(b["key"], []).append([b["t"], b["units"], b["paid"] / b["units"]])
    sold = sorted((r for r in view["auctions"] if r["outcome"] in ("sold", "partly") and r.get("itemKey") in lots),
                  key=lambda r: r.get("soldAt") or r.get("takenAt") or r["start"] or 0)
    for r in sold:
        left = r.get("soldUnits") or r.get("units") or 0
        for lot in lots[r["itemKey"]]:
            if left <= 0:
                break
            if lot[0] <= (r["start"] or 0):
                got = min(left, lot[1])
                lot[1] -= got
                left -= got
    out = {}
    for key, units in held.items():
        cost, covered = 0.0, 0
        for _, n, each in sorted(lots.get(key, ()), reverse=True):
            got = min(n, units - covered)
            cost, covered = cost + got * each, covered + got
            if covered >= units:
                break
        if covered:
            out[key] = [round(cost), covered]
    return out


def reposted(view):
    return {s["itemKey"]: {"reposts": s["reposts"], "lost": s["lost"]} for s in view["items"]
            if s.get("itemKey") and (s["reposts"] or s["lost"])}


def summaries(rows):
    by = {}
    for r in rows:
        nk = name_key(r.get("name")) or str(r.get("item"))
        s = by.setdefault(nk, {"name": r.get("name"), "item": r.get("item"), "bonus": r.get("bonus"),
                               "itemKey": item_key_of(r), "sold": 0, "expired": 0,
                               "cancelled": 0, "open": 0, "took": [], "events": [], "lost": 0, "unsold": [],
                               "starts": []})
        if r["start"] is not None:
            s["starts"].append(r["start"])
        if r["outcome"] in ("expired", "removed", "cancelled"):
            s["lost"] += (r["paid"] if r.get("paid") is not None else r.get("deposit")) or 0
            if r.get("ended") is not None:
                s["unsold"].append(r["ended"])
        if r["outcome"] in ("sold", "partly"):
            s["sold"] += 1
            s["events"].append((r.get("soldAt") or r.get("takenAt") or r["start"] or 0, "sold"))
            if r.get("took") is not None and r.get("sure") != "guess":
                s["took"].append(r["took"])
        elif r["outcome"] in ("expired", "removed"):
            s["expired"] += 1
            s["events"].append((r.get("ended") or r["start"] or 0, "expired"))
        elif r["outcome"] == "cancelled":
            s["cancelled"] += 1
        else:
            s["open"] += 1
    out = []
    for s in by.values():
        done = s["sold"] + s["expired"] + s["cancelled"]
        since = 0
        for _, what in sorted(s.pop("events")):
            since = 0 if what == "sold" else since + 1
        took = s.pop("took")
        unsold = min(s.pop("unsold"), default=None)
        starts = s.pop("starts")
        s["reposts"] = sum(1 for t in starts if unsold is not None and t >= unsold)
        out.append({**s,"saleRate": s["sold"] / done if done else None, "expiriesSince": since,
                    "took": sum(took) / len(took) if took else None, "tookN": len(took)})
    return sorted(out, key=lambda s: -(s["sold"] + s["expired"] + s["cancelled"]))
