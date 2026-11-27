# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import time

import numpy as np

import auctiondays as ad
from auction import in_house
import auctionmarket as am
import crafting
import gamedata
from counting import steps_of

DRAWS = 2000
SEED = 1613


class HouseSources(crafting.Sources):

    def __init__(self, pd, prices):
        super().__init__(None, pd, talk=0.0)
        self.prices = prices

    def recipe(self, item):
        return None

    def recipe_of(self, spell):
        line = self.cd.recipe(spell).get("prof")
        return {**self.info({"recipe": spell, "line": line, "profession": self.cd.names.get(int(line)) if line else None}),
                "known": True}

    def vendor(self, item):
        def make():
            price = self.pd.unit_price(item)
            if price is None:
                return None
            sellers = self.cd.sellers(item)
            return {"name": None, "price": price, "seconds": 0.0,
                    "limited": bool(sellers) and all(self.cd.limit(n, item) for n in sellers)}
        return self._kept("vendor", item, make)

    def auction(self, item, spots):
        p = (self.prices.get(str(item)) or {}).get("price")
        return {"price": p["price"], "cheaper": True, "seconds": 0.0} if p else None

    def spot(self, item, way, short=None):
        return None

    def quest(self, item):
        return None


def fees_of(rules):
    cut, deposit = (rules or {}).get("cut"), (rules or {}).get("deposit")
    return None if cut is None or deposit is None else (cut, deposit)


def sold_at(sims, item, units, fees):
    gross = sims * units
    if not fees:
        return gross
    cut, deposit = fees
    paid = max(deposit.get("least") or 0, (deposit.get("rate") or 0) * (gamedata.item_sell_price(item) or 0) * units)
    return gross * (1 - cut) - paid


def price_draws(row, rng, n=DRAWS):
    p = row["price"]
    sd = math.log(p["high"] / p["low"]) / (2 * ad.Z90) if p["low"] > 0 and p["high"] > p["low"] else 0.0
    return p["price"] * np.exp(sd * rng.standard_normal(n))


def figure(point, sims):
    low, high = np.quantile(sims, [am.LOW_Q, am.HIGH_Q])
    return {"mid": round(point), "low": round(float(low)), "high": round(float(high))}


def priced(prices, item):
    row = prices.get(str(item))
    return row if row and row.get("price") else None


def craft_row(src, spell, prices, fees, who):
    rec = src.recipe_of(spell)
    rng = np.random.default_rng([SEED, int(spell)])
    made = crafting.materials([{"item": rec["item"], "count": rec["makes"], "recipe": rec}], {}, src, mode=crafting.CHEAP)
    out = {"spell": int(spell), "name": rec["name"], "line": rec["line"], "profession": rec["profession"],
           "item": rec["item"], "makes": rec["makes"], "who": who, "product": None, "reagents": [], "tools": [],
           "value": None, "cost": None, "margin": None, "reagentsValue": None, "versus": None, "missing": [],
           "steps": None, "scans": None, "seen": None, "odds": None}
    used = []
    row = priced(prices, rec["item"])
    product = price_draws(row, rng) if row else None
    if row:
        p, s = row["price"], row.get("sales") or {}
        out["product"] = {"price": p["price"], "low": p["low"], "high": p["high"], "steps": p["steps"],
                          "scans": row["scans"], "seen": row["seen"], "day": s.get("day"), "dayLow": s.get("low"),
                          "dayHigh": s.get("high"), "daySteps": s.get("steps")}
        used.append(row)
    else:
        out["missing"].append("product")
    cost, cost_mid, value, value_mid = np.zeros(DRAWS), 0.0, np.zeros(DRAWS), 0.0
    costed = valued = True
    for r in made["rows"][1:]:
        if r["kind"] == "tool":
            out["tools"].append({"item": r["item"], "name": r["name"]})
        if r["kind"] != "material":
            continue
        item, n, way, market = r["item"], r["need"], r["pick"], priced(prices, r["item"])
        got = {"item": item, "name": r["name"], "count": n, "way": way, "unit": None, "low": None, "high": None,
               "sell": None, "sellUnit": None}
        draws = price_draws(market, rng) if market else None
        if way == "vendor":
            got["unit"] = r["ways"]["vendor"]["price"]
            cost, cost_mid = cost + got["unit"] * n, cost_mid + got["unit"] * n
        elif way == "auction":
            p = market["price"]
            got.update(unit=p["price"], low=p["low"], high=p["high"])
            cost, cost_mid = cost + draws * n, cost_mid + p["price"] * n
        else:
            costed = False
        pays = None if market else gamedata.item_sell_price(item)
        if market:
            got.update(sell="auction", sellUnit=market["price"]["price"])
            value = value + sold_at(draws, item, n, fees)
            value_mid += float(sold_at(np.array([market["price"]["price"]]), item, n, fees)[0])
            used.append(market)
        elif pays:
            got.update(sell="vendor", sellUnit=pays)
            value, value_mid = value + pays * n, value_mid + pays * n
        else:
            valued = False
        if way is None or got["sell"] is None:
            out["missing"].append(item)
        out["reagents"].append(got)
    if costed:
        out["cost"] = figure(cost_mid, cost)
    if row:
        worth = sold_at(product, rec["item"], rec["makes"], fees)
        worth_mid = float(sold_at(np.array([row["price"]["price"]]), rec["item"], rec["makes"], fees)[0])
        out["value"] = figure(worth_mid, worth)
        if costed:
            out["margin"] = figure(worth_mid - cost_mid, worth - cost)
        if valued:
            out["reagentsValue"] = figure(value_mid, value)
            out["versus"] = figure(worth_mid - value_mid, worth - value)
    lead = out["versus"] or out["margin"]
    if lead:
        out["scans"] = min(m["scans"] for m in used)
        seen = [m["seen"] for m in used if m.get("seen")]
        out["seen"] = min(seen) if seen else None
        out["steps"] = steps_of(max(abs(lead["mid"]), 1e-9), lead["low"], lead["high"], out["scans"])
    return out


def recipes_for(cd, prices, known, every):
    return [int(s) for s, r in cd.recipes.items()
            if r.get("makes") and (s in known or (every and priced(prices, r["makes"][0])))]


_kept = {}


def answer(hub, house=None, every=False, which="all"):
    import goods
    import planning
    got = hub.auction.house_of(house)
    only = goods.shown(hub, which)
    out = {"house": got["house"], "now": time.time(), "summarising": got["summarising"], "made": None, "newest": None,
           "fees": None, "recipes": [], "every": bool(every)}
    m = am.load(got["folder"]) if got["folder"] else None
    if not m:
        return out
    books = [b for k, b in hub.characters.recipe_books().items()
             if in_house(b["realm"], b["faction"], got["house"]) and (only is None or k in only)]
    known = {s for b in books for s in b["known"]}
    pd = planning.prof_data()
    stamp = (m.get("rests"), id(pd), tuple(sorted((b["name"], tuple(sorted(b["known"]))) for b in books)))
    slot = (got["folder"], bool(every), only is None)
    kept = _kept.get(slot)
    if kept and kept[0] == stamp:
        return {**kept[1], "now": out["now"], "summarising": got["summarising"]}
    prices = {r["item"]: r for r in m["items"]}
    fees = fees_of(m.get("rules"))
    src = HouseSources(pd, prices)
    rows = [craft_row(src, s, prices, fees, sorted(b["name"] for b in books if str(s) in b["known"]))
            for s in recipes_for(pd.cd, prices, known, every)]
    ids = sorted({r["item"] for r in rows if r["item"]} | {g["item"] for r in rows for g in r["reagents"]})
    infos = hub.auction.infos(ids) if ids else {}
    for r in rows:
        info = infos.get(str(r["item"])) or {}
        r.update(itemName=info.get("n") or pd.cd.item_name(r["item"]), q=info.get("q"), icon=info.get("icon"))
        for g in r["reagents"]:
            g["icon"] = (infos.get(str(g["item"])) or {}).get("icon")
    out.update(made=m.get("made"), newest=m.get("newest"), recipes=rows,
               fees=None if not fees else {"cut": fees[0], "deposit": fees[1]})
    _kept[slot] = (stamp, out)
    return out
