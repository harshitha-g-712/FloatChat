"""
Live check of nl_parser against the REAL Gemini API (no fakes).

Run from the project root, with your key in .env or the environment:

    USE_GEMINI=true GEMINI_API_KEY=... python tests/live_nl_parser_check.py
    python tests/live_nl_parser_check.py "your own question" "another one"

Calls are spaced by LIVE_DELAY seconds (default 13) to respect free-tier limits.

Prints, per question, which parser was used and the parsed fields, so you can
see whether Gemini's output passed validation or was rejected (and why).
"""

import logging
import os
import sys
import time

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BACKEND, "..", ".env"))
    load_dotenv(os.path.join(BACKEND, ".env"))
except ImportError:
    pass

os.environ.setdefault("USE_GEMINI", "true")

import gemini_service
from retrieval import nl_parser

# config.USE_GEMINI is read at import time; make sure the service sees the flag.
gemini_service.USE_GEMINI = os.environ.get("USE_GEMINI", "").lower() == "true"

QUESTIONS = [
    "What was the average temperature in January 2023?",
    "Show salinity between 100 and 500 dbar for float 2902758 in 2023",
    "Highest salinity recorded in Andaman Sea",
    "What is a thermocline?",
    "Who won the cricket world cup?",
    "Show temperature in March 2019",          # year/month in text, check no invention
    "average salinity near the surface",       # no literal numbers allowed
]

FIELDS = ("task", "variable", "stat", "year", "month", "platform_id",
          "pressure_min", "pressure_max", "named_region", "chart_type",
          "question_kind", "ambiguous")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="  [%(name)s] %(message)s")
    if not gemini_service.init_gemini():
        print("Gemini not initialised: set GEMINI_API_KEY (and install google-genai).")
        return 1
    questions = sys.argv[1:] or QUESTIONS
    # Free tier allows ~5 requests/minute; pause between calls (LIVE_DELAY secs).
    delay = float(os.environ.get("LIVE_DELAY", "13"))
    llm_used = 0
    for i, q in enumerate(questions):
        if i and delay > 0:
            time.sleep(delay)
        intent = nl_parser.parse_question(q)
        llm_used += intent["parser_used"] == "llm"
        print(f"\nQ: {q}\n  parser_used = {intent['parser_used']}")
        print("  " + ", ".join(f"{k}={intent.get(k)}" for k in FIELDS))
    print(f"\nLLM accepted for {llm_used}/{len(questions)} questions.")
    return 0 if llm_used else 2


if __name__ == "__main__":
    raise SystemExit(main())
