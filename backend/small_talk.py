"""Friendly replies for small talk (no web-framework imports, so it is easy to test).

``small_talk_reply(text, coverage)`` returns a reply when the WHOLE message is small talk
(greeting, "how are you", thanks, goodbye, a short acknowledgement, or "what can you do / help"),
otherwise ``None`` so the message goes through the normal question pipeline. A message that
contains anything else ("hi, average temperature in 2023") is never treated as small talk.
"""
import re
from typing import Optional

MAX_LEN = 80

# (category, regex). Matched against a normalised message (lower case, letters/digits/' only).
_PARTS = [
    ("greet", r"h+i+|h+e+y+|h+e+l+o+|he+l+l*o+|hlo+|hiya+|hai+|hy+|yo+|howdy|namaste|namaskar|vanakkam|hola|"
              r"good\s*(?:morning|mrng|afternoon|evening|day)|gm"),
    ("how",   r"how\s+(?:are|r)\s+(?:you|u|ya)(?:\s+doing|\s+today)?|how(?:\s+is|s)\s+it\s+going|how\s+you\s+doing|"
              r"how\s+do\s+you\s+do|(?:what|whats|wat)(?:\s+is|s)?\s+up|wassup|wazzup|sup"),
    ("thanks", r"thank\s+(?:you|u)(?:\s+so\s+much|\s+very\s+much|\s+a\s+lot)?|thanks?(?:\s+a\s+lot|\s+so\s+much|\s+a\s+ton)?|"
               r"thx|thanx|tysm|ty|many\s+thanks|much\s+appreciated|appreciate\s+it"),
    ("bye",   r"bye+|goodbye|good\s*night|gn|see\s+(?:you|ya)(?:\s+later|\s+soon)?|cya|take\s+care|ttyl"),
    ("ack",   r"ok(?:ay)?|kk?|cool|nice|great|awesome|perfect|got\s+it|alright|noted|no\s+problem"),
    ("addr",  r"there|bro|sir|madam|mam|maam|buddy|friend|dear|everyone|all|guys|team|bot|ai|floatchat|again|folks|mate|man|dude|assistant|please|pls"),
]
_TOKEN_RE = re.compile(r"\s*(?:" + "|".join(f"(?P<{n}>{p})" for n, p in _PARTS) + r")(?=\s|$)")

_HELP_RE = re.compile(
    r"^(?:help(?:\s+me)?|what\s+can\s+you\s+do|what\s+do\s+you\s+do|who\s+are\s+you|what\s+are\s+you|"
    r"(?:what|whats)(?:\s+is|s)?\s+floatchat|how\s+(?:do\s+i\s+|to\s+)use(?:\s+this|\s+floatchat|\s+it)?|"
    r"how\s+does\s+(?:this|it)\s+work|what\s+can\s+i\s+ask|what\s+should\s+i\s+ask|examples?|menu|commands)"
    r"(?:\s+(?:please|pls|bro|sir))?$")


def _normalise(text: str) -> str:
    t = (text or "").lower().replace("\u2019", "'").replace("`", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)      # punctuation and emoji become spaces
    t = t.replace("'", "")                    # what's -> whats
    return re.sub(r"\s+", " ", t).strip()


def _examples(coverage: str) -> str:
    return ("I can answer questions about ARGO ocean float data for the Bay of Bengal"
            f"{f' ({coverage})' if coverage else ''}. Try: 'What was the average temperature in March 2023?', "
            "'Compare salinity between January and June 2023', 'List floats in 2023', "
            "'Where did float 2902758 travel?' or 'What is a thermocline?'.")


def small_talk_reply(text: str, coverage: str = "") -> Optional[str]:
    raw = (text or "").strip()
    if not raw or len(raw) > MAX_LEN:
        return None
    norm = _normalise(raw)
    if not norm:
        # Only emoji / symbols (for example a waving-hand emoji): answer friendly; bare "???" is not small talk.
        return f"Hello! {_examples(coverage)}" if any(ord(c) > 127 for c in raw) else None
    if _HELP_RE.match(norm):
        return _examples(coverage)

    seen, pos = set(), 0
    while pos < len(norm):
        m = _TOKEN_RE.match(norm, pos)
        if not m or m.end() == pos:
            return None                       # something that is not small talk: use the normal pipeline
        seen.add(m.lastgroup)
        pos = m.end()
    seen.discard("addr")
    if not seen:
        return None                           # only "bro"/"sir"-style words
    if "bye" in seen:
        return "Goodbye! Come back any time to explore more ARGO ocean data."
    if "thanks" in seen:
        return "You're welcome! Ask me anything else about the Bay of Bengal ARGO data."
    if "greet" in seen or "how" in seen:
        lead = "Hello! I'm doing well, thanks for asking. " if "how" in seen else "Hello! "
        return lead + _examples(coverage)
    return "Sure! " + _examples(coverage)    # plain acknowledgement ("ok", "cool")