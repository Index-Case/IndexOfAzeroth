# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import datafiles

PATH = datafiles.data_path("books.json")


def load():
    return datafiles.load(PATH, None)


def had(book, done, bags, bank):
    if done is None:
        return None
    if book["quest"] in done:
        return "turned"
    if bags and bags.get(book["item"]):
        return "bags"
    if bank and bank["items"].get(book["item"]):
        return "bank"
    return None


def answer(characters):
    data = load()
    if not data:
        return None
    done, bags, bank = characters.game_said()
    books = [{**b, "had": had(b, done, bags, bank)} for b in data["books"]]
    count = sum(1 for b in books if b["had"] == "turned")
    rewards = [{**r, "done": done is not None and r["id"] in done,
                "open": done is not None and r.get("books") is not None and count >= r["books"]} for r in data["rewards"]]
    return {**{k: v for k, v in data.items() if k not in ("books", "rewards", "sources")}, "known": done is not None,
            "count": count if done is not None else None, "books": books, "rewards": rewards,
            "bankAt": bank["at"] if bank else None}
