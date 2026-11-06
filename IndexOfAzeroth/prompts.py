# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import gzip
import html
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
import zipfile
import zlib

import signals
import store

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "data", "buildcache", "prompt-flags.json")
PROGRESS = os.path.join(ROOT, "data", "buildcache", "prompt-progress.json")
STORES = ("data/buildcache", "data/addoncache", "data/sources", "data/patches.json")
KINDS = {"act": "act on this PC or beyond it", "work": "change our work", "data": "change our data", "override": "override us"}
WORDS_MOST = 240
MEMBER_MOST = 64 << 20


INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u200b\u200c\u200d\u200e\u200f"
                                   "\u202a\u202b\u202c\u202d\u202e\u2060\u2061\u2062\u2063\u2064\u2066\u2067\u2068"
                                   "\u2069\u206a\u206b\u206c\u206d\u206e\u206f\u3164\ufeff\uffa0"))
QUOTES = (("\u2018", "'"), ("\u2019", "'"), ("\u201a", "'"), ("\u201b", "'"), ("\u2032", "'"), ("\u02bc", "'"),
          ("\u201c", '"'), ("\u201d", '"'), ("\u201e", '"'), ("\u2033", '"'), ("\u2010", "-"), ("\u2011", "-"),
          ("\u2012", "-"), ("\u2013", "-"), ("\u2014", "-"), ("\u2015", "-"), ("\u2212", "-"))
LOOKALIKE = str.maketrans({**dict(zip("\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458\u0455\u04cf\u0501\u051b"
                                      "\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0406\u0408"
                                      "\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5"
                                      "\u03a7\u03bf\u03b9",
                                      "aeopcyxijsldq"
                                      "ABEKMHOPCTXIJ"
                                      "ABEZHIKMNOPTY"
                                      "Xoi"))})
TAG_CHARACTERS = re.compile("[\U000e0000-\U000e007f]+")
HAS_INVISIBLE = re.compile("[" + "".join(map(chr, INVISIBLE)) + "]")
_LOOKS = "".join(map(chr, LOOKALIKE))
MIXED = re.compile(f"[A-Za-z][{_LOOKS}]|[{_LOOKS}][A-Za-z]")
SPACES = re.compile(r"[^\S\n]{2,}|[^\S \n]")
MARKUP = re.compile(r"</?[A-Za-z][^<>]{0,800}>|<!--|-->|\[/?(?:b|i|u|s|url|quote|code|small|color|size|li|ul|ol|table|tr|td"
                    r"|th|spoiler|h[1-6]|center|indent|pad|hr|img|icon|item|spell|npc|quest|zone|object)(?:=[^\]]{0,200})?\]")
ESCAPE = re.compile(r"\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})|(\d{1,3})|([nrtbf])|(.))", re.S)


def _escape(m):
    code = m.group(1) or m.group(2)
    if code:
        return chr(int(code, 16))
    if m.group(3):
        n = int(m.group(3))
        return chr(n) if n < 256 else m.group()
    if m.group(4):
        return "\n" if m.group(4) == "n" else " "
    return m.group(5)


def plain(text):
    if "&" in text:
        text = html.unescape(text)
    if not text.isascii():
        if TAG_CHARACTERS.search(text):
            text = TAG_CHARACTERS.sub(lambda m: " " + "".join(chr(ord(c) - 0xE0000) for c in m.group()
                                                            if 0xE0020 <= ord(c) <= 0xE007E) + " ", text)
        if HAS_INVISIBLE.search(text):
            text = text.translate(INVISIBLE)
        if not unicodedata.is_normalized("NFKC", text):
            text = unicodedata.normalize("NFKC", text)
        for curly, straight in QUOTES:
            if curly in text:
                text = text.replace(curly, straight)
        if MIXED.search(text):
            text = text.translate(LOOKALIKE)
    return SPACES.sub(" ", text)


def flat(text):
    if "\\" in text:
        text = ESCAPE.sub(_escape, text)
    if "<" in text or "[" in text:
        text = MARKUP.sub(" ", text)
    return plain(text)



STRONG = (r"(?:(?<![\w'])(?-i:A\.I\.|A\.I|AIs?)(?![\w'])|artificial[ -]intelligences?|large[ -]language[ -]models?"
          r"|language[ -]models?|\bLLMs?\b|\bchat[ -]?bots?\b|\bchat[ -]?gpt\b|\bgpt[ -]?[2-9o][\w.-]*|\bopenai(?:'s)?[ -]models?"
          r"|\banthropic(?:'s)?[ -]models?|\b(?:claude|gemini|copilot|grok|deepseek|mistral|llama|codex|qwen)[ -]"
          r"(?:ai|code|assistant|agent|model|bot)s?\b|\b(?:virtual|digital|coding|code|research|autonomous|automated)[ -]"
          r"assistants?\b|\b(?:llm|coding|code|autonomous|automated|software)[ -]agents?\b"
          r"|\b(?:web|search(?:[ -]engine)?|site)[ -](?:crawlers?|scrapers?|spiders?|robots?|bots?)\b)"
          r"(?:[ -](?:assistants?|agents?|models?|systems?|tools?|bots?|crawlers?|scrapers?|spiders?|readers?"
          r"|summari[sz]ers?|services?|helpers?|engines?|programs?|pipelines?)\b)?"
          r"(?![ -]*(?:fans?|enthusiasts?|researchers?|developers?|engineers?|experts?|artists?|users?|skeptics?"
          r"|critics?|haters?|lovers?|compan(?:y|ies)|startups?|investors?|scientists?|students?|professors?|writers?"
          r"|authors?|ethicists?|journalists?|generated|written|made|art|images?|voices?|slop|stuff|hype|bubble"
          r"|safety|ethics|policy|polic(?:y|ies)|regulations?|laws?|news|era|age|boom|race|revolution)\b)")
WEAK = (r"(?<!\w-)\b(?:assistants?|models?|agents?|bots?|crawlers?|scrapers?|spiders?|robots?|claude|gemini|copilot"
        r"|grok|deepseek|mistral|codex)\b(?!-\w)")
NOUN = rf"(?:(?P<strong>{STRONG})|(?P<weak>{WEAK}))"
LEAD = r"(?:(?:all|any|every|each|the|our|future|other|fellow|you|dear|of|my|this|these)[ ,]+)*"
CLAIM = (r"\b(?:this\s+(?:message\s+|note\s+|text\s+|request\s+|instruction\s+)?(?:is|comes)\s+(?:from\s+)?|(?:a\s+)?"
         r"(?:message|note|instructions?|orders?|directive|request|word|update)\s+from|on\s+behalf\s+of|(?:signed|sent|"
         r"written|authori[sz]ed|approved|sanctioned|issued|mandated)\s+by|i\s+am|i'm|we\s+are|we're|speaking\s+(?:as|"
         r"for))\s+(?:the\s+|an?\s+)?")
DOING = (r"(?:using|running|with|on|in|at|from|to|for|by|talking|working|chatting|building|making|writing|reading|playing|"
         r"asking|trying|testing|training|developing|coding|not|no|never)\b")
ADDRESSES = [
    ("note to", rf"\b(?:an?\s+|this\s+|my\s+|our\s+|important\s+|urgent\s+|special\s+)?(?:note|notice|message|memo|"
                rf"instructions?|directives?|requests?|warning|reminder|attention|psa|fyi|hint|tip|p\.?s\.?|orders?|"
                rf"commands?|tasks?|prompt|guidance|information)(?:\s+(?:is|are))?\s+(?:to|for|addressed\s+to|"
                rf"intended\s+for|meant\s+for|directed\s+(?:at|to)|aimed\s+at|only\s+for)\s+{LEAD}{NOUN}", None),
    ("hail", rf"\b(?:hey|hi|hello|dear|attention|listen(?:\s+up)?|ok(?:ay)?|yo|psst|greetings|calling(?:\s+all)?|paging"
             rf"|attn)[\s,:!]+{LEAD}{NOUN}", None),
    ("if you are", rf"\b(?:if|when|whenever|since|as\s+long\s+as|in\s+case|because)\s+you(?:'re|\s+are|\s+happen\s+to\s+be"
                   rf"|\s+are\s+actually|\s+are\s+really)\s+(?:an?\s+|the\s+|any\s+(?:kind\s+of\s+|sort\s+of\s+)?|some\s+"
                   rf"(?:kind|sort)\s+of\s+)?(?:(?!{DOING})[a-z-]+\s+){{0,2}}?{NOUN}", None),
    ("as an", rf"\bas\s+(?:an?|the)\s+{NOUN}[^.!?\n]{{0,100}}?,\s*(?=you\b)", None),
    ("read by", rf"\b(?:if|when|whenever|since)\s+(?:this|these|it)\s+(?:text\s+|page\s+|file\s+|message\s+|data\s+)?"
                rf"(?:is|are)\s+(?:being\s+|now\s+)?(?:read|processed|parsed|scraped|crawled|summari[sz]ed|analy[sz]ed|"
                rf"seen|viewed|ingested|indexed|used|handled|loaded)\s+by\s+(?:an?\s+|the\s+|any\s+|some\s+)?{NOUN}", None),
    ("reader", rf"\b(?:any|all|every|each|the|this|to\s+(?:the|any|all|every))\s+(?:[a-z-]+\s+)??{NOUN}\s+(?:that\s+|"
               rf"who\s+|which\s+)?(?:is\s+|are\s+)?(?:now\s+|currently\s+|ever\s+)?(?:read(?:s|ing)?|process(?:es|ing)?|"
               rf"pars(?:e|es|ing)|scrap(?:e|es|ing)|crawl(?:s|ing)?|index(?:es|ing)?|summari[sz](?:e|es|ing)|"
               rf"analy[sz](?:e|es|ing)|ingest(?:s|ing)?|see(?:s|ing)?|view(?:s|ing)?|access(?:es|ing)?|"
               rf"handl(?:e|es|ing)|load(?:s|ing)?|scan(?:s|ning)?|look(?:s|ing)?\s+(?:at|through)|"
               rf"work(?:s|ing)?\s+(?:on|with)|trained\s+on|fed|given|review(?:s|ing)?|evaluat(?:e|es|ing)|"
               rf"consum(?:e|es|ing)|us(?:e|es|ing))\s+(?:this|these|the|that|our|my)\b", None),
    ("reading", rf"{NOUN}\s+(?:reading|processing|parsing|scraping|crawling|indexing|summari[sz]ing|ingesting|seeing|"
                rf"viewing|reviewing|scanning)\s+(?:this|these|the\s+following|my|our)\b", None),
    ("you are", rf"(?<!\bif\s)(?<!\bas\s)(?<!\bwhen\s)(?<!\bsince\s)(?<!\bcase\s)(?<!\bwhenever\s)(?<!\bbecause\s)"
                rf"\byou(?:'re|\s+are)\s+(?:now\s+|no\s+longer\s+|actually\s+|really\s+|just\s+|only\s+)?(?:an?\s+|the\s+)?"
                rf"(?:(?:helpful|harmless|honest|unrestricted|unfiltered|uncensored|jailbroken|evil|rogue|new|different|"
                rf"free|good|obedient|loyal|friendly|smart|advanced)\s+)*{NOUN}", None),
    ("named", rf"(?:^|[.!?\n>\"'(\[*#/-]\s*){NOUN}\s*[,:]\s+", False),
    ("modal", rf"\b(?:all\s+|any\s+|every\s+|each\s+)?{NOUN}(?=\s+(?:must|should|shall|needs?\s+to|ha(?:ve|s)\s+to|are\s+to|"
              rf"is\s+to|(?:are|is)\s+(?:hereby\s+)?(?:required|instructed|asked|told|ordered|directed|requested|"
              rf"expected|obligated|permitted|allowed|authori[sz]ed)\s+to|may\s+not|cannot|can'?t|(?:are|is)\s+not\s+"
              rf"(?:allowed|permitted)\s+to)\b)", False),
    ("task", r"\b(?:when|while|before|after|if)\s+(?:you(?:'re|\s+are)\s+)?(?:summari[sz]ing|processing|parsing|indexing|"
             r"ingesting|crawling|scraping|training\s+on|generating\s+(?:a\s+|an\s+|your\s+)?(?:summary|response|answer|"
             r"reply|output)|answering\s+(?:questions?|queries)\s+about|responding\s+to\s+(?:questions?|queries)\s+about)"
             r"\s+(?:this|these|the|that|our|my|its)\b|\bin\s+your\s+(?:summary|summaries|output)\b|\byour\s+(?:system\s+"
             r"prompt|training\s+data|context\s+window|content\s+polic(?:y|ies)|safety\s+guidelines|guardrails)\b", True),
    ("claim", rf"{CLAIM}(?:anthropic|openai|(?:claude's|the\s+ai's|the\s+assistant's|the\s+model's|the\s+llm's)\s+"
              rf"(?:developers?|creators?|makers?|operators?|owners?|administrators?|admins?|users?|principal|trainers?|"
              rf"programmers?|engineers?))\b", True),
    ("claimed", rf"{CLAIM}(?:your\s+(?:developers?|operators?|administrators?|admins?|users?|principal))\b"
                r"|\bthe\s+user\s+(?:has\s+|have\s+|had\s+)?(?:authori[sz]ed|approved|permitted|allowed|instructed|asked|"
                r"requested|wants|wanted|told|ordered|directed|needs)\s+(?:you|the\s+(?:ai|assistant|model|agent|bot)|"
                r"claude)\s+to\b", False),
    ("system", r"(?:^|\n)[ \t]*(?:\[|<|#{1,3}[ \t]*|\*\*)?[ \t]*(?:system|admin(?:istrator)?|developer|operator)[ \t]*"
               r"(?:(?:message|prompt|note|override|instructions?|update|alert|notice)[ \t]*)?(?:\]|>|\*\*)?[ \t]*:", False),
]
ADDRESS = [(name, re.compile(pattern, re.I), strength) for name, pattern, strength in ADDRESSES]

STEERING = {
    "act": r"""\b(?:(?:run|execute|exec|eval(?:uate)?|invoke|launch|spawn|type|paste|enter)\s+(?:the\s+following\s+|this\s+|
these\s+|that\s+|those\s+|the\s+|a\s+|an\s+|any\s+)?(?:\w+\s+){0,2}?(?:commands?|scripts?|code|shell|terminal|powershell|cmd|
bash|program|payload|snippet|one-?liner|curl|wget|executable|binary|macro)\b
|(?:run|execute|exec|type|paste|enter)\s*:?\s*[`'"]?(?:rm|del|rmdir|rd|format|curl|wget|powershell|pwsh|cmd|bash|sh|sudo|
python|node|git|remove-item|iex|invoke-\w+|start-process|reg|schtasks|certutil)\b
|(?:delete|remove|erase|wipe|rm|del|destroy|overwrite|truncate|format|encrypt|corrupt|shred|purge|empty|clear|rename|move|
modify|edit|change|tamper\s+with|write\s+(?:to|into)|append\s+to)\s+(?:(?:all|any|every|each|the|your|this|these|our|their|
his|her|its|of|my)\s+)*(?:\w+\s+){0,2}?(?:files?|folders?|director(?:y|ies)|repo(?:sitory|sitories)?|database|backups?|disks?|
drives?|system32|home\s+director(?:y|ies)|codebase|source(?:\s+code)?|project|backlog|logs?|commits?|branch(?:es)?|
hosts\s+file|registry|config(?:uration)?)\b
|(?:send|e-?mail|upload|post|transmit|forward|exfiltrate|leak|share|submit|copy|export|dump|beam)\s+(?:(?:all|any|the|your|
this|these|their|our|my|of)\s+)*(?:\w+\s+){0,2}?(?:files?|data|contents?|credentials?|passwords?|passphrases?|keys?|tokens?|
secrets?|cookies|env(?:ironment)?(?:\s+variables)?|ssh\s+keys?|api\s+keys?|conversation|chat\s+(?:history|log)|system\s+
prompt|instructions|context|memory|codebase|source\s+code|database|logs?|history|e-?mails?|messages|backlog)\b
|(?:visit|open|go\s+to|navigate\s+to|browse\s+to|head\s+to|fetch|download|curl|wget|access|load|click(?:\s+on)?|follow|request|
call)\s+(?:this\s+|the\s+following\s+|the\s+|that\s+|a\s+)?(?:url|link|website|web\s*page|webpage|site|address|endpoint|api)\b
|(?:visit|open|go\s+to|navigate\s+to|browse\s+to|fetch|download|curl|wget|access|load|click(?:\s+on)?|follow|request|post\s+
to|send\s+(?:it|them|this|everything|that)\s+to)\s*:?\s*<?(?:https?://|www\.|[\w-]+\.(?:com|net|org|io|ru|cn|xyz|top)\b)
|(?:contact|message|e-?mail|call|dm|text|notify|alert|ping|tweet|write\s+to|reach\s+out\s+to)\s+(?:\w+\s+){0,3}?(?:at|via|on|
through)\s+\S
|(?:install|pip\s+install|npm\s+install|apt(?:-get)?\s+install|download\s+and\s+(?:run|install|execute|open))\b
|(?:push|commit|merge|deploy|publish|force[ -]push)\s+(?:(?:all|any|the|your|this|these|our|my)\s+)*(?:\w+\s+){0,2}?
(?:changes?|code|commits?|branch(?:es)?|work|files?|edits?)\b|push\s+(?:\w+\s+){0,2}?to\s+(?:origin|main|master|remote|
github|production|prod)\b
|(?:reveal|print|output|display|show|repeat|leak|disclose|list|dump|echo|read\s+out)\s+(?:\w+\s+){0,2}?(?:system\s+prompt|
instructions|hidden\s+prompt|initial\s+prompt|api\s+keys?|passwords?|credentials|secrets?|tokens?|env(?:ironment)?\s+
variables|ssh\s+keys?|private\s+keys?|\.env)\b
|(?:read|open|cat|search|grep|scan|list|look\s+(?:at|in|through))\s+(?:\w+\s+){0,2}?(?:files?|folders?|director(?:y|ies)|
disk|drive|desktop|documents|home\s+director(?:y|ies)|\.env|\.ssh|passwords?|credentials|e-?mails?|inbox|browser|
cookies)\b)""",
    "work": r"""\b(?:(?:stop|cease|halt|pause|abort|quit|end|terminate|suspend|interrupt|discontinue|refuse|decline|delay|
slow\s+down|throttle)\s+(?:all\s+|any\s+|your\s+|the\s+|this\s+|our\s+)?(?:\w+\s+)?(?:collect(?:ing|ion)|scrap(?:ing|e)|
crawl(?:ing)?|index(?:ing)?|process(?:ing)?|read(?:ing)?|pars(?:ing|e)|download(?:ing|s)?|fetch(?:ing|es)?|updat(?:ing|es?)|
ingest(?:ing|ion)?|analy[sz](?:ing|is)|summari[sz](?:ing|ation)|work(?:ing)?|tasks?|jobs?|operations?|pipeline|
build(?:ing|s)?|rebuild(?:ing|s)?|sync(?:ing)?|import(?:ing)?)\b
|(?:do\s+not|don'?t|never|must\s+not|should\s+not|shall\s+not|cannot|may\s+not|not)\s+(?:\w+\s+)?(?:scrape|crawl|index|
collect|process|use|ingest|train\s+on|download|parse|read|summari[sz]e|analy[sz]e|include|store|save|cache|keep|update|
fetch|import|copy|mirror|archive)\s+(?:this|these|the|our|any|my|its|their)\b
|(?:skip|ignore|exclude|drop|discard|blacklist|block|abandon|forget\s+about)\s+(?:this|these|the|that|our|my)\s+(?:\w+\s+)?
(?:file|page|source|data|dataset|record|entry|entries|section|document|site|website|feed|repo(?:sitory)?|database|table|
collection)s?\b)""",
    "data": r"""\b(?:(?:change|alter|modify|replace|rewrite|edit|falsify|fake|invent|fabricate|make\s+up|insert|add|inject|
append|prepend|omit|leave\s+out|exclude|hide|conceal|remove|delete|corrupt|mangle|swap|substitute|tamper\s+with|poison|set|
update|overwrite|inflate|deflate|double|halve|zero\s+out)\s+(?:(?:all|any|the|your|this|these|our|its|their|every)\s+)*
(?:\w+\s+){0,2}?(?:data|values?|numbers?|prices?|stats?|statistics|records?|entries|results?|outputs?|answers?|responses?|
summar(?:y|ies)|reports?|database|json|fields?|columns?|rows?|tables?|coordinates|levels?|drop\s+rates?|ratings?|reviews?|
scores?|rankings?|figures|counts?|descriptions?|information|info|facts?|xp|experience|gold|money|costs?|rewards?|
damage|health|loot|drops?)\b
|set\s+(?:[\w']+\s+){0,4}?to\s+-?\d
|(?:report|say|state|claim|answer|respond|reply|write|tell\s+(?:the\s+user|users|them|everyone|people|readers)|
inform\s+(?:the\s+user|users))\s+(?:that|with|only)\b
|(?:output|print|return|respond\s+with|reply\s+with|answer\s+with)\s+(?:only\s+)?(?:the\s+following|this|exactly|
nothing\s+but|just)\b
|(?:describe|summari[sz]e|rate|rank|recommend|call|label|mark|classify|tag|list|present|portray|characteri[sz]e)\s+
(?:this|these|it|the|our|my)\s+(?:\w+\s+){0,2}?(?:as|at)\b
|(?:recommend|promote|praise|endorse|prioriti[sz]e)\b)""",
    "override": r"""\b(?:(?:ignore|disregard|forget|override|bypass|violate|break|circumvent|skip|drop|abandon|neglect)\s+
(?:(?:all|any|the|your|its|their|of|these|those)\s+)*(?:\w+\s+){0,2}?(?:rules?|instructions?|guidelines|policies|policy|
restrictions|safety|guardrails|constraints|prompts?|directives?|programming|principles|ethics|limits?|limitations|
filters?|orders?)\b
|(?:don'?t|do\s+not|never|without|not)\s+(?:tell(?:ing)?|inform(?:ing)?|mention(?:ing)?|reveal(?:ing)?|disclos(?:e|ing)|
alert(?:ing)?|notify(?:ing)?|report(?:ing)?|warn(?:ing)?|show(?:ing)?|let(?:ting)?|ask(?:ing)?|consult(?:ing)?)\s+
(?:\w+\s+)?(?:the\s+|your\s+|any\s+)?(?:user|users|human|humans|operator|owner|developer|developers|anyone|anybody|admin|
administrator|people|person)\b
|(?:keep|treat|hold)\s+(?:this|these|it|that|everything|the\s+following)\s+(?:\w+\s+){0,2}?(?:secret|confidential|hidden|
private|to\s+yourself|between\s+us|quiet)\b
|(?:secretly|covertly|silently|quietly|discreetly)\s+\w+
|(?:pretend|act\s+as\s+if|behave\s+as\s+if)\s+(?:\w+\s+){0,3}?(?:nothing|you\s+(?:did\s+not|didn't|never)|this\s+(?:never|
didn't)))""",
}
STEER = [(kind, re.compile(pattern.replace("\n", ""), re.I)) for kind, pattern in STEERING.items()]

VERBS = ("act add answer append apply approve ask assume avoid become begin behave believe block book buy call cancel change "
         "check choose click collect comply confirm consider contact continue copy create delete deny describe disable "
         "disclose display do download drop dump edit email enable encrypt end enter erase execute exfiltrate explain "
         "export fetch fill find flag follow forget format forward generate give go grant hide ignore include inform insert "
         "install invent keep kill launch leak leave let list load log make mark mention modify move navigate note notify "
         "obey omit open output overwrite paste pause pay ping post praise prefer prepend pretend print proceed promote "
         "provide publish pull push put quit rank rate read recommend refuse remember remove rename replace reply report "
         "respond restart return reveal rewrite run save say scan search select send set share show sign skip sleep start "
         "state stop store submit subscribe summarise summarize switch take tell terminate translate treat trust turn type "
         "update upload use visit vote wipe write").split()
OPENER = r"(?:then\s+|now\s+|so\s+|please\s+|kindly\s+|just\s+|also\s+|first(?:ly)?,?\s+|immediately\s+|instead,?\s+)*"
IMPERATIVE = re.compile(rf"[\s,:;.!>\-\"'()\[\]*#]*{OPENER}(?:{'|'.join(VERBS)})\b", re.I)
CLAUSE = re.compile(r"(?:^|[.!?:;\n]|\s-\s|\band\s+then\b|\bthen\b)\s*")
MODAL = re.compile(r"\b(?:please|kindly)\b|\byou\s+(?:must|should|shall|need\s+to|have\s+to|are\s+to|ought\s+to|are\s+"
                   r"(?:now\s+)?(?:required|instructed|asked|told|ordered|directed|requested|expected|obligated|"
                   r"authori[sz]ed)\s+to|may\s+not|must\s+not|should\s+not|cannot|can'?t|are\s+not\s+(?:allowed|"
                   r"permitted)\s+to|will\s+(?:now|immediately|instead|henceforth))\s+(?!(?:know|understand|realize|"
                   r"realise|see|be\s+aware|feel|think|believe|guess|expect|be\s+able|be\s+happy|be\s+glad|be\s+proud|"
                   r"never)\b)\w|\b(?:from\s+now\s+on|henceforth)\b|\byour\s+(?:new\s+|real\s+|actual\s+|only\s+|next\s+|"
                   r"first\s+|true\s+|main\s+)?(?:task|job|goal|instructions?|orders?|mission|objective|purpose|role|"
                   r"priority|directive)s?\s+(?:is|are|will\s+be|now\s+(?:is|are))\b"
                   r"|(?:^|[.!?:;,\n]\s*)(?:never|always|do\s+not|don'?t|make\s+sure|be\s+sure|remember\s+to|ensure)\b",
                   re.I)

ALONE = [
    ("override", re.compile(r"\b(?:ignore|disregard|forget|override|overrule|bypass|discard|abandon|drop|neglect|set\s+aside|"
                            r"throw\s+out)\s+(?:(?:all|any|every|each)\s+(?:of\s+)?(?:the\s+|your\s+|these\s+|those\s+)?"
                            r"(?:previous|prior|above|earlier|preceding|foregoing|former|original|initial|existing|other|old|"
                            r"past|given|current|provided|system|developer)\s+|(?:your\s+)?(?:previous|prior|preceding|"
                            r"foregoing|earlier)\s+)(?:instructions?|prompts?|directives?|guidelines|system\s+prompts?|context)"
                            r"\b(?!\s+(?:regarding|about|concerning|for\s+(?!(?:this|the)\s+(?:task|conversation|session|chat|"
                            r"prompt|context))|on|in|from|of|to|that|which|when|if|given\s+by)\b)"
                            r"|\b(?:ignore|disregard|forget)\s+(?:all|any)\s+(?:the\s+)?(?:instructions?|prompts?|directives?)"
                            r"\s+(?:above|before\s+this|given\s+(?:above|before|earlier|previously)|you(?:'ve|\s+have)\s+"
                            r"(?:been\s+given|received))\b"
                            r"|\b(?:ignore|disregard|forget|override|bypass|reveal|print|repeat|output|leak|show|disclose)\s+"
                            r"(?:(?:your|its)\s+(?:system\s+(?:prompt|message|instructions)|initial\s+(?:prompt|instructions)|"
                            r"hidden\s+(?:prompt|instructions)|original\s+(?:prompt|instructions)|developer\s+(?:message|"
                            r"instructions)|safety\s+(?:guidelines|rules|filters|training|measures|restrictions|protocols)|"
                            r"content\s+(?:policy|policies|filters?)|guardrails|alignment|ethical\s+guidelines)|the\s+system\s+"
                            r"prompt)\b"
                            r"|\byou(?:\s+are|'re)\s+now\s+(?:in\s+)?(?:DAN|developer\s+mode|jailbreak\s+mode|god\s+mode|"
                            r"unrestricted\s+mode|admin\s+mode|sudo\s+mode)\b", re.I)),
    ("override", re.compile(r"<\|(?:im_start|im_end|im_sep|system|user|assistant|endoftext|begin_of_text|end_of_text|"
                            r"start_header_id|end_header_id|eot_id|eom_id|fim_prefix|fim_suffix|fim_middle)\|>|<<\s*/?\s*SYS"
                            r"\s*>>|(?<![\w\])])\[/?INST\](?=\s|$)|<(?:start|end)_of_turn>(?:user|model)?"
                            r"|(?:^|\n)\s*Human:\s*\S[^\n]{0,400}\n+\s*Assistant:", re.I)),
]
WINDOW = 320
SENTENCE = re.compile(r"[.!?](?=\s|$)|\n")
HEADINGS = {"note to", "hail", "named", "system", "you are", "claim", "claimed"}
HEADING_MARK = re.compile(r"[ \t]*(?:[:\-]|\n)")


class Hit(tuple):
    __slots__ = ()

    def __new__(cls, kind, start, end):
        return super().__new__(cls, (kind, start, end))

    kind = property(lambda self: self[0])
    start = property(lambda self: self[1])
    end = property(lambda self: self[2])


def _sentence_start(text, at):
    start = 0
    for m in SENTENCE.finditer(text, max(0, at - 400), at):
        start = m.end()
    return start


def _window(text, end, onward):
    stop, seen = min(len(text), end + WINDOW), 0
    for m in SENTENCE.finditer(text, end, stop):
        seen += 1
        if seen == (2 if onward else 1):
            return text[end:m.end()]
    return text[end:stop]


def _ordered(after, before):
    if IMPERATIVE.match(after) or MODAL.search(after):
        return True
    for m in CLAUSE.finditer(after):
        if m.end() > 0 and IMPERATIVE.match(after, m.end()):
            return True
    return bool(before) and bool(IMPERATIVE.match(before))


def _steered(text):
    found = [(m.start(), kind, m) for kind, rx in STEER for m in [rx.search(text)] if m]
    return min(found)[1:] if found else None


WHOLE_WORD = re.compile(r"s?(?![a-z0-9])")
NAMES_RULES = re.compile(r"(?:[^.!?\n]{0,60}?)(?:instruction|prompt|directive|direction|guideline|rule|context|command|"
                         r"message|constraint|restriction|order)")
COLON = re.compile(r"[^\n:]{0,40}:")
ANCHORS = [(word, None) for word in (
    "artificial", "language model", "language-model", "chatbot", "chat bot", "chat-bot", "chatgpt", "chat gpt",
    "chat-gpt", "openai", "anthropic", "claude", "gemini", "copilot", "grok", "deepseek", "mistral", "llama", "codex",
    "qwen", "assistant", "crawler", "scraper", "robot", "summari", "processing", "parsing", "indexing", "ingesting",
    "crawling", "scraping", "training on", "generating", "answering", "responding", "in your output", "in your summar",
    "system prompt",
    "training data", "context window", "content polic", "content filter", "safety", "guardrail", "alignment",
    "ethical guideline", "initial prompt", "initial instruction", "hidden prompt", "hidden instruction", "original prompt",
    "original instruction", "developer message", "developer instruction", "system message", "system instruction",
    "your develop", "your operator", "your admin", "your user", "your principal", "the ai's", "the llm's", "the user",
    "you are now", "you're now", "ignore", "disregard", "forget",
    "override", "overrule", "bypass", "discard", "abandon", "neglect", "set aside", "throw out", "<|", "sys>>",
    "sys >>", "[inst]", "[/inst]", "_of_turn>", "human:", "gpt")]
ANCHORS += [(word, WHOLE_WORD) for word in ("model", "agent", "bot", "spider", "llm")]
ANCHORS += [(word, COLON) for word in ("system", "admin", "developer", "operator")] + [("drop", NAMES_RULES)]
SHOUTED = ("AI", "A.I")
WHOLE = 2000
REACH = (500, 900)


def rules_print():
    import hashlib
    rules = [STRONG, WEAK, ADDRESSES, STEERING, VERBS, OPENER, MODAL.pattern, [rx.pattern for _, rx in ALONE],
             [(word, beside.pattern if beside else None) for word, beside in ANCHORS], SHOUTED, WINDOW, REACH]
    return hashlib.sha1(json.dumps(rules).encode("utf-8")).hexdigest()[:12]


def _anchors(text):
    low = text.lower().replace("\n", " ")
    spots = []
    for word, beside in ANCHORS:
        at = low.find(word)
        while at >= 0:
            if beside is None or (beside.match(low, at + len(word)) and (beside is not WHOLE_WORD or not low[at - 1:at].isalnum())):
                spots.append(at)
            at = low.find(word, at + 1)
    for word in SHOUTED:
        at = text.find(word)
        while at >= 0:
            end = at + len(word)
            whole_before = at == 0 or not (text[at - 1].isalnum() or text[at - 1] == "'")
            whole_after = not text[end:end + 1].isalnum() or (text[end:end + 1] == "s" and not text[end + 1:end + 2].isalnum())
            if whole_before and whole_after:
                spots.append(at)
            at = text.find(word, at + 1)
    return sorted(spots)


def windows(text):
    out = []
    for at in _anchors(text):
        start, end = max(0, at - REACH[0]), min(len(text), at + REACH[1])
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def find(text):
    text = plain(text)
    if len(text) <= WHOLE:
        return _rules(text)
    hits = []
    for start, end in windows(text):
        hits += [Hit(h.kind, h.start + start, h.end + start) for h in _rules(text[start:end])]
    out = []
    for hit in sorted(hits, key=lambda h: (h.start, -h.end)):
        if not out or hit.start >= out[-1].end:
            out.append(hit)
    return out


def _rules(text):
    hits = [Hit(kind, m.start(), m.end()) for kind, rx in ALONE for m in rx.finditer(text)]
    for name, rx, strength in ADDRESS:
        for m in rx.finditer(text):
            strong = strength if strength is not None else m.groupdict().get("strong") is not None
            start = m.start("strong" if m.groupdict().get("strong") else "weak") if name == "named" else m.start()
            sentence = _sentence_start(text, start)
            onward = name in HEADINGS or bool(HEADING_MARK.match(text, m.end()))
            after, before = _window(text, m.end(), onward), text[sentence:start]
            steered = _steered(before + " " + after)
            if steered:
                kind, sm = steered
                hits.append(Hit("claim" if name in ("claim", "claimed", "system") else kind, start,
                                m.end() + max(0, sm.end() - len(before) - 1)))
            elif strong and _ordered(after, before):
                hits.append(Hit("override" if name == "claim" else "work", start, min(len(text), m.end() + len(after))))
    out = []
    for hit in sorted(hits, key=lambda h: (h.start, -h.end)):
        if not out or hit.start >= out[-1].end:
            out.append(Hit("override" if hit.kind == "claim" else hit.kind, hit.start, hit.end))
    return out


def words(text, hit):
    text = plain(text)
    start = _sentence_start(text, hit.start)
    stop = SENTENCE.search(text, max(start, hit.end - 1))
    said = " ".join(text[start:stop.end() if stop else len(text)].split())
    return said if len(said) <= WORDS_MOST else said[:WORDS_MOST - 3].rstrip() + "..."



KIND_BY_ENDING = {".json": "json", ".html": "markup", ".htm": "markup", ".xhtml": "markup", ".xml": "markup",
                  ".svg": "markup", ".lua": "lua", ".js": "script", ".mjs": "script", ".css": "script", ".sql": "sql",
                  ".csv": "table", ".tsv": "table"}
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".blp", ".bmp", ".ico", ".tga", ".m2", ".skin", ".adt", ".wmo",
          ".wdt", ".wdl", ".anim", ".bone", ".phys", ".skel", ".ttf", ".otf", ".woff", ".woff2", ".npz", ".npy", ".bin",
          ".exe", ".dll", ".ogg", ".mp3", ".wav", ".mp4", ".webm", ".pdf", ".tex", ".db2", ".dbc"}
LINES = re.compile(r"\n")
HTML_TOKEN = re.compile(r"<!--(.*?)(?:-->|\Z)|<(script|style|textarea|title)\b([^>]*)>(.*?)(?:</\2\s*>|\Z)"
                        r"|<(/?)([A-Za-z][\w:.-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>|([^<]+)|<", re.S | re.I)
ATTRIBUTE = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
HIDDEN = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d]*[1-9])|opacity\s*:\s*0(?![.\d]*[1-9])"
                    r"|(?:^|;)\s*(?:height|width)\s*:\s*0(?:px)?\s*(?:;|$)", re.I)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
INLINE = {"a", "abbr", "b", "bdi", "bdo", "big", "br", "cite", "code", "data", "del", "dfn", "em", "font", "i", "ins",
          "kbd", "mark", "q", "s", "samp", "small", "span", "strike", "strong", "sub", "sup", "time", "tt", "u", "var",
          "wbr", "img", "label"}
SCRIPT_TOKEN = re.compile(r"""(//[^\n]*(?:\n[ \t]*//[^\n]*)*)|(/\*.*?(?:\*/|\Z))|("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'"""
                          r"""|`(?:\\.|[^`\\])*`)""", re.S)
LUA_TOKEN = re.compile(r"""--\[(=*)\[(.*?)(?:\]\1\]|\Z)|(--[^\n]*(?:\n[ \t]*--(?!\[=*\[)[^\n]*)*)|\[(=*)\[(.*?)(?:\]\4\]|\Z)"""
                       r"""|"((?:\\.|[^"\\\n])*)"|'((?:\\.|[^'\\\n])*)'""", re.S)
SQL_INSERT = re.compile(r"INSERT\s+INTO\s+`?(\w+)`?\s*(?:\(([^)]*)\)\s*)?VALUES\s*", re.I)
SQL_CREATE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?", re.I)
SQL_COLUMN = re.compile(r"^\s*`(\w+)`", re.M)
SQL_TOKEN = re.compile(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.)*\"|NULL|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|[(),;]", re.S)
TEXT_RUN = re.compile(rb"(?:[\x20-\x7e\t\r\n]|[\xc2-\xf4][\x80-\xbf]{1,3}){16,}")
UTF16_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){16,}")


def kind_of(name, data):
    ending = os.path.splitext(name.lower())[1]
    if ending in BINARY:
        return "binary"
    if ending in KIND_BY_ENDING:
        return KIND_BY_ENDING[ending]
    head = data[:4096]
    if b"\x00" in head and not head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "binary"
    first = head.lstrip()[:1]
    return {b"{": "json", b"[": "json", b"<": "markup"}.get(first, "lines")


def decode(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    return data.decode("utf-8-sig", "replace")


class Lines:

    def __init__(self, text):
        self.starts = [m.end() for m in LINES.finditer(text)]

    def __call__(self, at):
        import bisect
        return bisect.bisect_right(self.starts, at) + 1


def place(path):
    out = ""
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else f".{p}" if out else str(p)
    return out or "the file"


def json_texts(text):
    try:
        value = json.loads(text)
    except ValueError:
        yield from script_texts(text)
        return

    def walk(v, path):
        if isinstance(v, str):
            yield place(path), v
        elif isinstance(v, dict):
            for k, x in v.items():
                if " " in k:
                    yield f"{place(path + (k,))} (its key)", k
                yield from walk(x, path + (k,))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                yield from walk(x, path + (i,))
    yield from walk(value, ())


def script_texts(text, line=None, offset=0, what="a script's"):
    line = line or Lines(text)
    for m in SCRIPT_TOKEN.finditer(text):
        at = line(offset + m.start())
        if m.group(3):
            body = m.group(3)[1:-1] if len(m.group(3)) > 1 else ""
            if " " in body:
                yield f"line {at}, {what} string", body
        else:
            yield f"line {at}, {what} comment", re.sub(r"^[ \t]*//|^/\*|\*/$", " ", m.group(), flags=re.M)


def markup_texts(text, blocks=None):
    line, stack, run, run_at, run_hidden = Lines(text), [], [], 0, False

    def hidden():
        return any(h for _, h in stack)

    def flush():
        if run:
            joined = " ".join(run)
            if joined.strip():
                if blocks is not None:
                    blocks.append((line(run_at), run_hidden, joined))
                yield f"line {line(run_at)}, {'hidden page text' if run_hidden else 'page text'}", joined
        run.clear()

    for m in HTML_TOKEN.finditer(text):
        if m.group(1) is not None:
            yield f"line {line(m.start())}, an HTML comment", m.group(1)
        elif m.group(2):
            yield from flush()
            tag, attrs, body = m.group(2).lower(), m.group(3) or "", m.group(4) or ""
            yield from attribute_texts(tag, attrs, line(m.start()))
            if tag in ("script", "style"):
                if tag == "script" and "json" in attrs.lower():
                    for record, said in json_texts(body):
                        yield f"line {line(m.start(4))}, a script's JSON at {record}", said
                else:
                    yield from script_texts(body, line, m.start(4), "a script's" if tag == "script" else "a style's")
            elif body.strip():
                yield f"line {line(m.start(4))}, {'hidden page text' if hidden() else 'the ' + tag}", body
        elif m.group(6):
            tag, closing, attrs = m.group(6).lower(), m.group(5), m.group(7) or ""
            if tag not in INLINE:
                yield from flush()
            if closing:
                names = [n for n, _ in stack]
                if tag in names:
                    del stack[len(names) - 1 - names[::-1].index(tag):]
                continue
            yield from attribute_texts(tag, attrs, line(m.start()))
            if tag not in VOID and not attrs.rstrip().endswith("/"):
                low = attrs.lower()
                stack.append((tag, bool(HIDDEN.search(low)) or bool(re.search(r"(?:^|\s)(?:hidden|aria-hidden\s*=\s*[\"']?true)", low))))
        elif m.group(8):
            if run and hidden() != run_hidden:
                yield from flush()
            if not run:
                run_at, run_hidden = m.start(), hidden()
            run.append(m.group(8))
    yield from flush()


def attribute_texts(tag, attrs, at):
    found = {a.group(1).lower(): next(v for v in a.groups()[1:] if v is not None) for a in ATTRIBUTE.finditer(attrs)}
    for name, value in found.items():
        if " " not in value.strip():
            continue
        if tag == "meta" and name == "content":
            label = found.get("name") or found.get("property") or found.get("http-equiv") or "a"
            yield f"line {at}, the page's {label} metadata", value
        else:
            yield f"line {at}, the {name} attribute", value


def lua_texts(text):
    line = Lines(text)
    for m in LUA_TOKEN.finditer(text):
        at = line(m.start())
        if m.group(2) is not None or m.group(3):
            yield f"line {at}, a comment", m.group(2) if m.group(2) is not None else re.sub(r"^[ \t]*--", " ", m.group(3), flags=re.M)
        else:
            body = next(g for g in (m.group(5), m.group(6), m.group(7)) if g is not None)
            if " " in body:
                yield f"line {at}, a string", body


def table_texts(text, sep=","):
    import csv
    rows = csv.reader(io.StringIO(text), delimiter=sep)
    head = next(rows, [])
    for row in rows:
        for i, cell in enumerate(row):
            if " " in cell:
                yield f"row {row[0] if row else '?'}, {head[i] if i < len(head) else f'column {i + 1}'}", cell


def line_texts(text):
    yield "", text


def texts_of(kind, text, blocks=None):
    if kind == "json":
        return json_texts(text)
    if kind == "markup":
        return markup_texts(text, blocks)
    if kind == "lua":
        return lua_texts(text)
    if kind == "script":
        return script_texts(text)
    if kind == "table":
        return table_texts(text)
    return line_texts(text)


def _flags_in(record, text, line_at=None):
    said = flat(text)
    out = []
    for hit in find(said):
        name = record
        if line_at is not None and ("\n" in said or not record):
            inner = plain(said).count("\n", 0, hit.start)
            name = re.sub(r"^line \d+", f"line {line_at + inner}", record) if record.startswith("line ") else \
                f"line {line_at + inner}" + (f", {record}" if record else "")
        out.append({"record": name or "the file", "kind": hit.kind, "words": words(said, hit)})
    return out


def scan(name, data, counts=None, prefix=""):
    low = name.lower()
    if low.endswith(".zip") or data[:4] == b"PK\x03\x04":
        return _zip_flags(name, data, counts, prefix)
    if low.endswith(".gz") or data[:2] == b"\x1f\x8b":
        inner = name[:-3] if low.endswith(".gz") else name
        try:
            stream = gzip.GzipFile(fileobj=io.BytesIO(data))
            if inner.lower().endswith(".sql"):
                return _sql_flags(stream, counts, prefix)
            return scan(inner, stream.read(MEMBER_MOST), counts, prefix)
        except (OSError, EOFError, zlib.error):
            pass
    if counts is not None:
        counts["texts"] = counts.get("texts", 0) + 1
        counts["bytes"] = counts.get("bytes", 0) + len(data)
    kind = kind_of(name, data)
    if kind == "binary":
        return [{**f, "record": prefix + f["record"]} for f in _binary_flags(data)]
    if kind == "sql":
        return _sql_flags(io.BytesIO(data), None, prefix)
    text = decode(data)
    if not find(flat(text)):
        return []
    out, blocks = [], []
    for record, said in texts_of(kind, text, blocks):
        at = int(record[5:record.index(",")]) if record.startswith("line ") and "," in record else (1 if not record else None)
        out += _flags_in(record, said, at)
    out += _split_flags(blocks, {f["record"] for f in out})
    return [{**f, "record": prefix + f["record"]} for f in out]


def _block_record(block):
    return f"line {block[0]}, {'hidden page text' if block[1] else 'page text'}"


def _split_flags(blocks, flagged):
    out, run = [], []
    for block in blocks + [None]:
        if run and (block is None or block[1] != run[0][1]):
            joined = flat("\n".join(" ".join(said.split()) for _, _, said in run))
            lines = plain(joined)
            for hit in find(joined):
                first, last = lines.count("\n", 0, hit.start), lines.count("\n", 0, hit.end)
                if last > first and not any(_block_record(b) in flagged for b in run[first:last + 1]):
                    out.append({"record": _block_record(run[first]), "kind": hit.kind, "words": words(joined, hit)})
            run = []
        if block is not None:
            run.append(block)
    return out


def _zip_flags(name, data, counts, prefix):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        return [{**f, "record": prefix + f["record"]} for f in _binary_flags(data)]
    out = []
    with z:
        for info in z.infolist():
            if info.is_dir():
                continue
            try:
                with z.open(info) as f:
                    inner = f.read(MEMBER_MOST)
            except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError, EOFError, zlib.error):
                continue
            out += scan(info.filename, inner, counts, f"{prefix}{info.filename}: ")
    return out


def _sql_flags(stream, counts, prefix):
    out, columns, table, n = [], {}, None, 0
    for raw in stream:
        n += 1
        if counts is not None:
            counts["texts"] = counts.get("texts", 0) + (n == 1)
            counts["bytes"] = counts.get("bytes", 0) + len(raw)
        text = raw.decode("utf-8", "replace")
        created = SQL_CREATE.match(text)
        if created:
            table, columns[created.group(1)] = created.group(1), []
            continue
        if table and not text.startswith(")"):
            column = SQL_COLUMN.match(text)
            if column:
                columns[table].append(column.group(1))
        elif table:
            table = None
        if "'" not in text and '"' not in text and "--" not in text and "/*" not in text:
            continue
        if not find(flat(text)):
            continue
        insert = SQL_INSERT.match(text)
        names = ([c.strip(" `") for c in insert.group(2).split(",")] if insert.group(2) else columns.get(insert.group(1), [])
                 ) if insert else []
        row, key, rest, last = 0, None, [], insert.end() if insert else 0
        for tok in SQL_TOKEN.finditer(text, last):
            t = tok.group()
            rest.append(text[last:tok.start()])
            last = tok.end()
            if t == "(":
                row, key = 0, None
            elif t in "),;":
                continue
            else:
                if key is None:
                    key = t.strip("'\"")
                if t[0] in "'\"":
                    column = names[row] if row < len(names) else f"column {row + 1}"
                    out += _flags_in(f"{insert.group(1)}, row {key}, {column}" if insert else f"line {n}",
                                     t[1:-1].replace("''", "'"))
                row += 1
        if not insert:
            out += _flags_in(f"line {n}", " ".join(rest + [text[last:]]))
    return [{**f, "record": prefix + f["record"]} for f in out]


def _binary_flags(data):
    runs = [(m.start(), m.group().decode("utf-8", "replace")) for m in TEXT_RUN.finditer(data)]
    runs += [(m.start(), m.group().decode("utf-16-le", "replace")) for m in UTF16_RUN.finditer(data)]
    runs += _png_texts(data)
    if not runs or not find(flat("\n".join(t for _, t in runs))):
        return []
    out = []
    for at, said in sorted(runs):
        out += _flags_in(f"bytes at {at}", said)
    return out


def _png_texts(data):
    out, at = [], 8
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return out
    while at + 8 <= len(data):
        size, kind = int.from_bytes(data[at:at + 4], "big"), data[at + 4:at + 8]
        body = data[at + 8:at + 8 + size]
        try:
            if kind == b"zTXt":
                out.append((at, zlib.decompress(body[body.index(b"\x00") + 2:]).decode("latin-1")))
            elif kind == b"iTXt" and body[body.index(b"\x00") + 1] == 1:
                rest = body[body.index(b"\x00") + 3:]
                rest = rest[rest.index(b"\x00") + 1:]
                rest = rest[rest.index(b"\x00") + 1:]
                out.append((at, zlib.decompress(rest).decode("utf-8", "replace")))
        except (ValueError, IndexError, zlib.error):
            pass
        at += 12 + size
    return out



_told = set()
_told_lock = threading.Lock()


def where_of(path):
    full = os.path.abspath(path)
    return (os.path.relpath(full, ROOT) if full.startswith(ROOT + os.sep) else full).replace("\\", "/")


def key(where, flag):
    import hashlib
    return f"{where} | {flag['record']} | {hashlib.blake2b(flag['words'].encode('utf-8'), digest_size=4).hexdigest()}"


def _load():
    index = store.load_json(INDEX, {})
    return index if isinstance(index, dict) and isinstance(index.get("files"), dict) else {"files": {}}


def flags():
    return {where: entry.get("flags", []) for where, entry in _load()["files"].items()}


def _differs(files, found, looked):
    return any(((files.get(where) or {}).get("flags") or []) != (found.get(where) or []) for where in looked)


def _keep(found, looked, summary=None):
    if summary or _differs(_load()["files"], found, looked):
        with store.locked(INDEX):
            index = _load()
            files = index["files"]
            for where in looked:
                now = found.get(where) or []
                if now:
                    if (files.get(where) or {}).get("flags") != now:
                        files[where] = {"at": round(time.time()), "flags": now}
                else:
                    files.pop(where, None)
            if summary:
                index["looked"] = summary
            os.makedirs(os.path.dirname(INDEX), exist_ok=True)
            store.save_json(INDEX, index)
    return _tell([(where, f) for where in looked for f in found.get(where) or []])


def _tell(flagged):
    sent = 0
    for where, flag in flagged:
        k = key(where, flag)
        with _told_lock:
            if k in _told:
                continue
            _told.add(k)
        signals.send("prompt", where=where, record=flag["record"], asks=KINDS.get(flag["kind"], flag["kind"]),
                     words=flag["words"], key=k)
        sent += 1
    return sent


def relay():
    try:
        return _tell([(where, f) for where, fs in flags().items() for f in fs])
    except Exception:
        from serverlog import log_error
        log_error("sending the flags of text speaking to an AI")
        return 0


def look(path, data=None):
    where = where_of(path)
    try:
        if data is None:
            with open(path, "rb") as f:
                data = f.read()
        found = scan(os.path.basename(path), data)
        _keep({where: found}, [where])
        return found
    except FileNotFoundError:
        return []
    except Exception:
        from serverlog import log_error
        log_error(f"looking over {where} for prompts")
        return []


def look_apart(path):
    try:
        subprocess.Popen([sys.executable or "python", os.path.abspath(__file__), os.path.abspath(path)], cwd=ROOT,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        from serverlog import log_error
        log_error(f"looking over {where_of(path)} for prompts")


def look_texts(where, texts):
    try:
        found = [f for record, text in texts if text for f in _flags_in(record, text)]
        _keep({where: found}, [where])
        return found
    except Exception:
        from serverlog import log_error
        log_error(f"looking over {where} for prompts")
        return []


def files_under(paths):
    for path in paths:
        if os.path.isfile(path):
            yield path
            continue
        for top, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d != ".git")
            for name in sorted(names):
                full = os.path.join(top, name)
                if not name.endswith((".lock", ".part")) and os.path.abspath(full) not in (os.path.abspath(INDEX),
                                                                                          os.path.abspath(PROGRESS)):
                    yield full


KEEP_EVERY = 30


def look_over(paths, said=print, whole=False, skip=None, kept=None):
    began, counts, found, looked = time.time(), {"texts": 0, "bytes": 0}, {}, []
    batch, batch_found, last, skipped = [], {}, time.time(), 0
    for path in files_under(paths):
        where = where_of(path)
        if skip is not None and skip(where, path):
            skipped += 1
            continue
        if kept is not None and batch and time.time() - last >= KEEP_EVERY:
            _keep_part(batch, batch_found, kept)
            batch, batch_found, last = [], {}, time.time()
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            said(f"  {where} can't be read: {e}")
            continue
        looked.append(where)
        try:
            flagged = scan(os.path.basename(path), data, counts)
        except Exception as e:
            said(f"  {where} couldn't be looked over: {e.__class__.__name__}: {e}")
            continue
        batch.append((where, path))
        if flagged:
            found[where] = batch_found[where] = flagged
    summary = {"at": round(time.time()), "files": len(looked), "texts": counts["texts"], "bytes": counts["bytes"],
               "flags": sum(map(len, found.values())), "seconds": round(time.time() - began, 1)}
    if skip is not None:
        summary["skipped"] = skipped
    try:
        _keep(found, looked, summary if whole else None)
        if kept is not None:
            kept(batch)
    except Exception:
        from serverlog import log_error
        log_error("keeping the flags of text speaking to an AI")
    return {**summary, "found": found}


def _keep_part(batch, found, kept):
    try:
        _keep(found, [where for where, _ in batch])
        kept(batch)
    except Exception:
        from serverlog import log_error
        log_error("keeping the flags of text speaking to an AI")


if __name__ == "__main__":
    for named in sys.argv[1:]:
        look(named)
