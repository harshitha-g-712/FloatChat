"""Regions outside the dataset / knowledge base (pure helpers, no web framework)."""
import re
from typing import List

UNSUPPORTED_REGION_RE = re.compile(
    r"\b(arabian sea|red sea|persian gulf|gulf of (?:aden|oman|mexico)|mediterranean|atlantic|pacific|"
    r"southern ocean|arctic|antarctic\w*|south china sea|north sea|baltic|caribbean)\b", re.IGNORECASE)


def unsupported_regions(text: str) -> List[str]:
    """Distinct out-of-coverage region names mentioned in ``text`` (title-cased, in order)."""
    seen: List[str] = []
    for m in UNSUPPORTED_REGION_RE.finditer(text or ""):
        name = m.group(1).title()
        if name not in seen:
            seen.append(name)
    return seen


def _join(names: List[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def knowledge_region_notice(text: str) -> str:
    """Opening sentence for a knowledge answer when the question names a region we do not cover.

    Returns '' when no such region is named. It is placed BEFORE the Bay of Bengal answer.
    """
    names = unsupported_regions(text)
    if not names:
        return ""
    return (f"Note: this knowledge base and the bundled dataset cover only the Bay of Bengal, so I have no "
            f"notes or data on the {_join(names)}, and I can't compare it with the Bay of Bengal. "
            f"What I can tell you is about the Bay of Bengal:\n\n")
