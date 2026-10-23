"""Letters, requests and talking points written by Nemotron 3 Ultra, with the templates in actions.py as backup.

Code works out every fact first (amounts, dates, order and flight numbers, the rule's name) and hands Ultra those
facts as plain lines. Ultra writes the subject, the body and, where the template has one, the spoken script. Code
then checks the result the way pipeline/cancel.py checks the cancel email:
  - every placeholder the template has ("[your name]", "[account number]") is kept, and no new one appears;
  - no links of any kind (links sit next to the letter, from the rules data or search results);
  - every number in it appears in the facts (so no new amount, date, account or order number), and so does every
    month and weekday it names;
  - no threats, legal talk or promises ("lawsuit", "attorney", "guarantee"), and within length limits.
Anything that fails means the template is used, and a "fallback" trace row says which check failed. Dashes and
exclamation marks are swapped for plain punctuation (the wording rules) rather than rejected.
ActionMessage.written_by says who wrote it: the model id, or "template".
"""

from __future__ import annotations

import re

from .. import llm
from ..models import ActionMessage, ActionPrep
from ..pipeline import grounded
from ..trace import record

STAGE = "letter"
SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "script": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["subject", "body", "script"],
    "additionalProperties": False,
}
PROMPT = """Write a short {what}. The person sends it themselves; ClawBack never sends anything.
Facts (use only these; never add numbers, dates, prices, account or order numbers, names or links that are not here):
{facts}
Keep these placeholders exactly as written, where they belong: {placeholders}
{script_rule}
Style: plain and polite, short sentences, under {words} words in the body, end with [your name]. No links. No dashes.
No exclamation marks. No threats, no legal talk beyond naming the rule in the facts, no promises of a result.
Return JSON: {{"subject": str, "body": str, "script": [str]}}"""
SCRIPT_RULE = ('Also write "script": 2 to 5 short things to say on a call or in a chat, one sentence each, '
               "using the same facts.")
NO_SCRIPT = 'Set "script" to an empty list.'

PLACEHOLDER = re.compile(r"\[[^\[\]\n]{1,40}\]")
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTH_WORD = re.compile(r"\b(" + "|".join([*grounded.MONTHS, *(m[:3] for m in grounded.MONTHS), "sept"]) + r")\b",
                         re.I)
_BANNED = re.compile(r"\b(?:lawsuits?|sue|suing|attorneys?|lawyers?|legal action|courts?|guarantee[ds]?|promise[ds]?|"
                     r"demand(?:s|ed)?|threat\w*|immediately or)\b", re.I)
_DASHES = re.compile("\\s*[" + chr(0x2014) + chr(0x2013) + "]\\s*")


def _months(text: str) -> set[str]:
    out = set()
    for m in _MONTH_WORD.finditer(text):
        word = m.group(1).lower()
        # "may" is also a verb: count it only when a day number follows ("May 3").
        if word == "may" and not re.match(r"\s+\d", text[m.end():]):
            continue
        out.add(word[:3])
    return out


def _days(text: str) -> set[str]:
    low = text.lower()
    return {d for d in _DAYS if re.search(rf"\b{d}\b", low)}


def tidy(text: str) -> str:
    """The wording rules: no long dashes, no exclamation marks, tidy spaces."""
    text = _DASHES.sub(", ", text).replace("!", ".")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def check(subject, body, script, facts: str, placeholders: list[str], needs_script: bool) -> str | None:
    """None when Ultra's wording passes every check, else the reason it failed."""
    if not (isinstance(subject, str) and isinstance(body, str) and isinstance(script, list)):
        return "had the wrong shape"
    if not all(isinstance(s, str) for s in script):
        return "had the wrong shape"
    if not subject.strip() or len(subject) > 140 or not 40 <= len(body) <= 2000:
        return "was too short or too long"
    if needs_script and not 1 <= len(script) <= 8:
        return "left out the talking points"
    lines = script if needs_script else []
    if any(len(s) > 300 for s in lines):
        return "had a talking point that was too long"
    text = "\n".join([subject, body, *lines])
    if missing := [p for p in placeholders if p not in body]:
        return f"dropped the placeholder {missing[0]}"
    if extra := [p for p in PLACEHOLDER.findall(text) if p not in placeholders]:
        return f"added the placeholder {extra[0]}"
    if grounded.URL.search(text):
        return "had a link"
    allowed = facts + "\n" + " ".join(placeholders)
    if extra_numbers := grounded.numbers_in(text) - grounded.numbers_in(allowed):
        return f"used a number that isn't in the facts ({sorted(extra_numbers)[0]:g})"
    if _months(text) - _months(allowed) or _days(text) - _days(allowed):
        return "named a date that isn't in the facts"
    if m := _BANNED.search(text):
        return f"used the word {m.group(0).lower()!r}"
    if re.search(r"[<>{}]", text):
        return "had markup in it"
    return None


def write(user_id: str, kind: str, prep: ActionPrep, what: str, facts: list[str], words: int = 150) -> ActionPrep:
    """Ultra rewrites the template's message (and script) from `facts`. The template stays when there's no key,
    no message to write, the call fails, or the result fails a check."""
    if prep.message is None or not llm.available():
        return prep
    placeholders = list(dict.fromkeys(PLACEHOLDER.findall(prep.message.body)))
    needs_script = prep.script is not None
    facts_text = "\n".join(f"- {line}" for line in facts)
    data, res = llm.chat_json(
        user_id, STAGE, "reason",
        [{"role": "user", "content": PROMPT.format(
            what=what, facts=facts_text, placeholders=", ".join(placeholders) or "(none)",
            script_rule=SCRIPT_RULE if needs_script else NO_SCRIPT, words=words)}],
        SCHEMA, max_tokens=1200,
    )
    if data is None or res is None:
        record(user_id, STAGE, "code", status="fallback", note=f"{kind}: Ultra didn't answer, so the template is used")
        return prep
    subject, body = data.get("subject"), data.get("body")
    script = data.get("script") if isinstance(data.get("script"), list) else None
    if isinstance(subject, str) and isinstance(body, str):
        subject, body = tidy(subject), tidy(body)
    if script is not None:
        script = [tidy(s) if isinstance(s, str) else s for s in script]
    if why := check(subject, body, script, facts_text + "\n" + prep.message.body, placeholders, needs_script):
        record(user_id, STAGE, "code", status="fallback", note=f"{kind}: Ultra's wording {why}, so the template is used")
        return prep
    message = ActionMessage(to=prep.message.to, subject=subject, body=body, written_by=res.model)
    return prep.model_copy(update={"message": message, "script": script if needs_script else prep.script})
