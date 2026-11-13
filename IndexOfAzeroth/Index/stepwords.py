# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import re

import director_rules
import words

VERBS = frozenset((
    "Pick", "Use", "Speak", "Turn", "Kill", "Collect", "Escort", "Go", "Wait", "Set", "Train", "Learn", "Sell", "Buy",
    "Repair", "Craft", "Make", "Grind", "Gather", "Mine", "Take", "Raise", "Reach", "Fish", "Get", "Find", "Open", "Fill",
    "Hand", "Perform",
    "Accompany", "Activate", "Answer", "Ask", "Assist", "Bring", "Burn", "Capture", "Carry", "Catch", "Check", "Claim",
    "Cleanse", "Climb", "Confront", "Defeat", "Defend", "Deliver", "Destroy", "Discover", "Drink", "Eat", "Enter",
    "Examine", "Explore", "Feed", "Fight", "Follow", "Free", "Guard", "Heal", "Help", "Hunt", "Inspect", "Investigate",
    "Jump", "Kneel", "Leap", "Light", "Listen", "Locate", "Look", "Lure", "Mark", "Obtain", "Offer", "Place", "Plant",
    "Pray", "Protect", "Punish", "Purify", "Read", "Receive", "Recruit", "Release", "Report", "Rescue", "Retrieve",
    "Return", "Ride", "Ring", "Salute", "Scout", "Search", "Seek", "Show", "Sit", "Slay", "Stand", "Summon", "Survive",
    "Talk", "Tame", "Toss", "Travel", "Venture", "Visit", "Wake", "Watch"))
DO = "Do"
REASON = "both.reason."
COUNTED = {"hearth": "min", "trip": "n"}
CLAUSE = re.compile(r",\s+")
PUNCT = ".!?"


def verb_first(text):
    word = (text or "").split(maxsplit=1)
    return bool(word) and word[0] in VERBS


def fronted(text):
    text = (text or "").strip()
    if not text:
        return None
    if text.split(maxsplit=1)[0] == DO and " " in text:
        text = f"Perform {text.split(maxsplit=1)[1]}"
    if verb_first(text):
        return text
    parts = CLAUSE.split(text, maxsplit=1)
    if len(parts) == 2 and parts[1][:1].islower() and verb_first(parts[1][:1].upper() + parts[1][1:]):
        rest, end = parts[1], ""
        if rest[-1:] in PUNCT:
            rest, end = rest[:-1], rest[-1]
        lead = parts[0][:1].lower() + parts[0][1:] if not parts[0][1:2].isupper() else parts[0]
        return f"{rest[:1].upper()}{rest[1:]}, {lead}{end}"
    return None


def the(name):
    first = name.split(maxsplit=1)[0] if name else ""
    return name if first.casefold() in ("the", "a", "an") or first.endswith("'s") else f"the {name}"


def same_name(a, b):
    return a.casefold().rstrip(PUNCT) == b.casefold().rstrip(PUNCT)


def pickup(quest, giver=None, thing=False, maybe=False, item=None):
    if item:
        return f"Use {item} to start {'its quest' if same_name(item, quest) else quest}"
    if not giver:
        return f"Pick up {quest}"
    if thing:
        return f"Pick up {quest}" if same_name(giver, quest) else f"Pick up {quest} at {the(giver)}"
    return f"Speak to {giver}" if maybe else f"Pick up {quest} from {giver}"


def turnin(quest, giver=None, thing=False):
    if not giver:
        return f"Turn in {quest}"
    if thing:
        return f"Turn in {quest}" if same_name(giver, quest) else f"Turn in {quest} at {the(giver)}"
    return f"Turn in {quest} to {giver}"


KIND_VERBS = {"kill": "Kill", "loot": "Collect", "use": "Use", "talk": "Speak to"}
GO = "Go to"


def objective(q, t, sentence):
    own = t.get("text")
    if own and verb_first(own):
        return own
    title = t.get("title") or t["name"]
    count = f"{t['count']} " if t.get("count", 1) > 1 else ""
    verb = KIND_VERBS.get(t.get("kind"))
    if verb:
        return f"{verb} {count}{title}"
    return next((s for s in (fronted(own), fronted(sentence(q, t["name"]))) if s), f"{GO} {title}")


def game_objective(q, said, sentence):
    return fronted(sentence(q, said[0])) or fronted("; ".join(said)) or f"{GO} {'; '.join(said)}"


def run(dungeon):
    return f"Go into {dungeon}"


def escort(npc):
    return f"Escort {npc}"


def names(xs):
    xs = list(dict.fromkeys(x for x in xs if x))
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def said(step, text):
    step["text"] = text
    name = step.get("questName") if step.get("quest") is not None else None
    if name and name not in text:
        step["forQuest"] = name
    else:
        step.pop("forQuest", None)
    return step


WORDS = {"offer": lambda a: words.say("both.reason.offer", a), "bind": lambda a: words.say("both.reason.bind", a),
         "hearth": lambda a: words.say("both.reason.hearth", a), "opens": lambda a: words.say("both.reason.opens", a),
         "message": lambda a: words.say("both.reason.message", a),
         "within": lambda a: words.say("both.reason.within", a) if a.get("npc") else words.say("both.reason.within-thing", a),
         "inside": lambda a: words.say("both.reason.inside", a),
         "early": lambda a: words.say("both.reason.early", a), "trip": lambda a: words.say("both.reason.trip", a),
         "flight": lambda a: words.say("both.reason.flight", a),
         "flightpass": lambda a: words.say("both.reason.flightpass", a), "bags": lambda a: words.say("both.reason.bags", a),
         "worn": lambda a: words.say("both.reason.worn", a), "low": lambda a: words.say("both.reason.low", a),
         "group": lambda a: words.say("both.reason.group", a), "ownrun": lambda a: words.say("both.reason.ownrun", a)}
ORDER = tuple(WORDS)


def place(step, towns=None):
    if step.get("kind") == "dungeon":
        return step.get("questName")
    at = step.get("at") or ()
    town = director_rules.town(towns, step.get("inst"), *at[:2]) if towns and len(at) >= 2 else None
    return town or step.get("zone")


def reason_words(code, args):
    n = args.get(COUNTED.get(code))
    one = words.say(f"{REASON}{code}.one", args) if n == 1 else None
    return one or WORDS[code](args)


def give(step, code, **args):
    have = step.get("reason")
    args = {k: v for k, v in args.items() if v not in (None, "")}
    if (not have or ORDER.index(have[0]) > ORDER.index(code)) and reason_words(code, args) is not None:
        step["reason"] = [code, args]
    return step


def drop(step, codes):
    if (step.get("reason") or [None])[0] in codes:
        del step["reason"]
    return step
