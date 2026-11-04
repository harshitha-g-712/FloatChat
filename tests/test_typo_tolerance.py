"""Typo tolerance: fixes known misspellings, never touches numbers/IDs or correct text."""
import ast
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from typo_tolerance import correct_typos  # noqa: E402
from retrieval.nl_parser import parse_question  # noqa: E402

MISSPELLINGS = [
    ("avarage temprature in march 2023", "average temperature in march 2023"),
    ("averge salinty in febuary 2023", "average salinity in february 2023"),
    ("maximun pressure for float 1900123", "maximum pressure for float 1900123"),
    ("minimun temperture at 500 dbar", "minimum temperature at 500 dbar"),
    ("compre salinity between janury and april", "compare salinity between january and april"),
    ("show profiel R1900123_001", "show profile R1900123_001"),
    ("tempreture of the bay of bangal", "temperature of the bay of bengal"),
    ("highst temperatrue in april 2023", "highest temperature in april 2023"),
    ("salinty in the andeman sea", "salinity in the andaman sea"),
    ("avrage tempurature in septmber", "average temperature in september"),
    ("wermest day", "warmest day"),
    ("trajectry of float 2902345", "trajectory of float 2902345"),
    ("depth profle for float 1900121", "depth profile for float 1900121"),
    ("compair temperature of march and april", "compare temperature of march and april"),
    ("prssure at 2000 dbar", "pressure at 2000 dbar"),
    ("averege temprature novemeber", "average temperature november"),
    ("Avarage Salinty", "Average Salinity"),
    ("minimun salinity in decembr 2023", "minimum salinity in december 2023"),
    ("coldst temperature in febrary", "coldest temperature in february"),
    ("saltyest water in the bay of bengal", "saltiest water in the bay of bengal"),
]


def test_at_least_15_misspellings_fixed():
    assert len(MISSPELLINGS) >= 15
    for bad, good in MISSPELLINGS:
        fixed, changes = correct_typos(bad)
        assert fixed == good, (bad, fixed, good)
        assert changes


def test_numbers_and_ids_never_change():
    for q in [
        "average temperature of float 1900123 in 2023",
        "profile R1900123_045 salinity",
        "float 2902345 at 2000 dbar between 10 and 20 N",
        "show 1900121_12 temprature",
    ]:
        fixed, _ = correct_typos(q)
        assert re.findall(r"[0-9][0-9_]*", fixed) == re.findall(r"[0-9][0-9_]*", q)
        assert re.findall(r"R?\d{5,}(?:_\d+)?", fixed) == re.findall(r"R?\d{5,}(?:_\d+)?", q)


CORRECT = [
    "average temperature in march 2023", "What is the thermocline?", "month by month salinity",
    "warmest month in 2023", "show me floats in the Bay of Bengal", "Hello", "what does salty mean",
    "maximum pressure in may", "compare march and april salinity", "which float has most profiles",
]


def test_correct_questions_unchanged():
    for q in CORRECT:
        assert correct_typos(q) == (q, [])


def test_existing_test_questions_unchanged():
    """Every question-like string literal in the other test files must pass through unchanged."""
    checked = 0
    for path in glob.glob(os.path.join(os.path.dirname(__file__), "test_*.py")):
        if path.endswith(("test_typo_tolerance.py", "test_round5.py", "test_new_years.py")):  # these contain deliberate misspellings
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                if 8 < len(v) < 140 and " " in v and "\n" not in v and re.search(r"[a-z]{3}", v):
                    assert correct_typos(node.value)[0] == node.value, node.value
                    checked += 1
    assert checked > 20


def test_misspelled_question_parses_like_correct_one():
    keys = ("task", "variable", "stat", "month", "year", "pressure_max")
    fixed, _ = correct_typos("avarage temprature in march 2023")
    got = parse_question(fixed)
    want = parse_question("average temperature in march 2023")
    assert {k: got.get(k) for k in keys} == {k: want.get(k) for k in keys}
    assert got["variable"] == "temperature" and got["stat"] == "avg" and got["month"] == 3 and got["year"] == 2023
