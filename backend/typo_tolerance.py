"""Small, safe typo-tolerance step that runs before question parsing.

Design (deliberately conservative):
- Only standalone alphabetic words of 6+ letters (so 5-letter words such as match/march are never touched) are considered. A token that touches a
  digit or underscore (float IDs, profile IDs, years, "R1900123") is never examined,
  so numbers and identifiers cannot change.
- A word is corrected only if it is NOT already a known word, and a single vocabulary
  word matches it with difflib ratio >= CUTOFF and the same first letter.
- The vocabulary is fixed (below); nothing is learned from the user or the database.
- Short month typos ("Aprl 2023", "Mrch 2023") get one extra, narrower rule: an unknown 4-5 letter
  word that sits directly before a four-digit year is matched against the month names only
  (difflib ratio >= 0.8, same first letter). Without this the month was silently dropped and the
  answer covered the whole year. 4-5 letter words anywhere else are still never changed.
"""
import re
from difflib import SequenceMatcher, get_close_matches
from typing import List, Tuple

CUTOFF = 0.8
MIN_LEN = 6

_MONTHS = [
    "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december",
]

VOCAB = sorted(set(_MONTHS + [
    # statistics
    "average", "averages", "maximum", "minimum", "highest", "lowest", "warmest",
    "coldest", "saltiest", "freshest", "median", "standard", "deviation", "trend",
    "range", "total", "count",
    # variables
    "temperature", "temperatures", "salinity", "pressure", "pressures", "density",
    "oxygen", "depth", "depths",
    # actions / objects
    "compare", "compared", "comparison", "between", "profile", "profiles", "float",
    "floats", "trajectory", "surface", "monthly", "show", "chart", "plot", "latest",
    "coverage", "measurements", "observations", "similar",
    # regions
    "bengal", "andaman", "arabian", "northern", "southern", "eastern", "western",
    "central", "ocean", "monsoon",
]))

# Correctly spelled words that are close to a vocabulary word but must never be changed.
KNOWN_OK = frozenset("""
    about above after before below could would should which where there their these those
    other first second third water thermocline halocline pycnocline sensor sensors argo
    sampled sample samples measured measure measures values value level levels layer layers
    mixed mixing summer winter spring autumn season seasons years yearly daily weekly
    explain describe define meaning means mean what when does happen happens during
    pressing pressed presses presents present preset flowing floating floated flight
    profiled profiling profit proper propose protein protect problem produce product
    ranges ranged ranger ranging count counts counted counter country counting
    depths depth dense density densely mediam median medium media meter meters
    marine mariner market march marsh martin margin mature measure
    salty saline salts salted saliva salinas
    comparing compares compare compared comparable
    totals total totally totaled
    coastal central centre centred center centers
    southern southwest southeast northern northwest northeast eastern western
    trends trending trended tendency
    latest later latter lately
    highest higher height heights lowest lower lowly
    average averages averaged averaging
    similar similarly similarity
    surface surfaces surfaced
    between betwixt
    chart charts charted
    plots plotted plotting
    shows showed shown showing
    oceans oceanic oceans
    oxygen oxygens
    fresher fresh freshly warmer warm colder cold saltier cooler cool deeper shallower higher lower
    warmth colder coldly freshwater freshen freshens freshened match matches matched matching
    measurement measurements measurer monsoons regions region plotly
    month months monthly year years yearly week weeks today yesterday
""".split())

_FULL_MONTHS = _MONTHS + ["may"]
_MONTH_ABBREV = frozenset("jan feb mar apr may jun jul aug sep sept oct nov dec".split())
_PRE_YEAR = re.compile(r"(?<![\w])([A-Za-z]{4,5})(?=\s+(?:19|20)\d\d(?![\w]))")
_TOKEN = re.compile(r"(?<![\w])([A-Za-z]{%d,})(?![\w])" % MIN_LEN)
_ALL_KNOWN = frozenset(VOCAB) | KNOWN_OK


def correct_typos(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Return (corrected_text, [(original, replacement), ...]).

    Case is preserved for the first letter (``Temprature`` -> ``Temperature``).
    """
    if not text:
        return text, []
    changes: List[Tuple[str, str]] = []

    def _fix(m: "re.Match[str]") -> str:
        word = m.group(1)
        low = word.lower()
        if low in _ALL_KNOWN:
            return word
        cands = [c for c in get_close_matches(low, VOCAB, n=3, cutoff=CUTOFF) if c[0] == low[0]]
        if not cands:
            return word
        # Refuse ambiguous matches: the runner-up must be clearly worse.
        # (Singular/plural pairs such as temperature/temperatures share a stem and are fine.)
        if len(cands) > 1 and not (cands[1].startswith(cands[0]) or cands[0].startswith(cands[1])):
            r0 = SequenceMatcher(None, low, cands[0]).ratio()
            r1 = SequenceMatcher(None, low, cands[1]).ratio()
            if r0 - r1 < 0.05:
                return word
        fixed = cands[0]
        if word[0].isupper():
            fixed = fixed[0].upper() + fixed[1:]
        changes.append((word, fixed))
        return fixed

    def _fix_month(m: "re.Match[str]") -> str:
        word = m.group(1)
        low = word.lower()
        if low in _ALL_KNOWN or low in _MONTH_ABBREV or low in _FULL_MONTHS:
            return word
        cands = [c for c in get_close_matches(low, _FULL_MONTHS, n=2, cutoff=CUTOFF) if c[0] == low[0]]
        if len(cands) != 1:  # none, or ambiguous
            return word
        fixed = cands[0]
        if word[0].isupper():
            fixed = fixed[0].upper() + fixed[1:]
        changes.append((word, fixed))
        return fixed

    out = _TOKEN.sub(_fix, text)
    out = _PRE_YEAR.sub(_fix_month, out)
    return out, changes
