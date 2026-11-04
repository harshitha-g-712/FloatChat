"""
FloatChat – nl_parser tests (offline; Gemini is always faked).
Runs with pytest or `python -m unittest tests.test_nl_parser`.
"""

import copy
import json
import os
import sys
import unittest
from unittest.mock import patch

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND)

import rule_intent
from config import ALLOWED_REGIONS
from retrieval import nl_parser
from retrieval.nl_parser import LLMParseError, parse_question, validate_llm_output


def good(**over):
    base = {
        "task": "stat", "variable": "temperature", "stat": "avg",
        "year": 2023, "month": 1, "platform_id": None,
        "pressure_range": None, "region": None,
        "chart_type": "none", "question_kind": "data",
    }
    base.update(over)
    return base


def fake(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return lambda prompt: raw


Q = "What was the average temperature in January 2023?"


class TestValidation(unittest.TestCase):
    def test_valid_result_accepted(self):
        out = validate_llm_output(good(), Q)
        self.assertEqual(out["year"], 2023)
        self.assertEqual(out["month"], 1)

    def test_fenced_json_tolerated(self):
        validate_llm_output("```json\n" + json.dumps(good()) + "\n```", Q)

    def test_invalid_json_rejected(self):
        for raw in ["not json", "", "[]", '{"a":', "null", '{"task": NaN}']:
            with self.subTest(raw=raw), self.assertRaises(LLMParseError):
                validate_llm_output(raw, Q)

    def test_duplicate_keys_rejected(self):
        raw = json.dumps(good()).replace('"stat": "avg"', '"stat": "avg", "stat": "max"')
        with self.assertRaises(LLMParseError):
            validate_llm_output(raw, Q)

    def test_unexpected_and_missing_fields_rejected(self):
        extra = good(); extra["sql"] = "DROP TABLE profiles"
        with self.assertRaises(LLMParseError):
            validate_llm_output(extra, Q)
        short = good(); del short["region"]
        with self.assertRaises(LLMParseError):
            validate_llm_output(short, Q)

    def test_invalid_enums_rejected(self):
        for field, val in [("task", "drop"), ("variable", "oxygen"), ("stat", "median"),
                           ("stat", None), ("chart_type", "pie"), ("chart_type", None),
                           ("region", "Pacific"), ("region", "bay of bengal"),
                           ("question_kind", "other"), ("variable", ["temperature"])]:
            with self.subTest(field=field, val=val), self.assertRaises(LLMParseError):
                validate_llm_output(good(**{field: val}), Q)

    def test_type_and_range_rejections(self):
        for field, val in [("year", "2023"), ("year", 2023.0), ("year", True), ("year", 1800),
                           ("month", 13), ("month", 0), ("month", "1"), ("month", True),
                           ("platform_id", 2902758), ("platform_id", "123")]:
            with self.subTest(field=field, val=val), self.assertRaises(LLMParseError):
                validate_llm_output(good(**{field: val}), Q)

    def test_hallucinated_year_rejected(self):
        with self.assertRaises(LLMParseError):
            validate_llm_output(good(year=2022), Q)
        # A year only as part of a longer number is not a literal year.
        with self.assertRaises(LLMParseError):
            validate_llm_output(good(year=2023, month=None), "float 12023 temperature")

    def test_hallucinated_month_rejected(self):
        with self.assertRaises(LLMParseError):
            validate_llm_output(good(month=6), Q)
        validate_llm_output(good(month=1), "average temperature in 2023-01")

    def test_hallucinated_platform_id_rejected(self):
        q = "Show temperature profile for float 2902758"
        ok = good(task="float_detail", platform_id="2902758", year=None, month=None)
        validate_llm_output(ok, q)
        with self.assertRaises(LLMParseError):
            validate_llm_output(good(task="float_detail", platform_id="2902759", year=None, month=None), q)
        # profile-id style mention counts as a literal mention of the platform
        validate_llm_output(ok, "profile 2902758_139 temperature")
        # not a substring of a longer digit run
        with self.assertRaises(LLMParseError):
            validate_llm_output(ok, "float 29027581 temperature")

    def test_pressure_range_literal_check(self):
        q = "average salinity between 100 and 500 dbar in 2023"
        ok = good(variable="salinity", month=None, pressure_range={"min": 100, "max": 500})
        out = validate_llm_output(ok, q)
        self.assertEqual(out["pressure_range"], {"min": 100.0, "max": 500.0})
        for bad in [{"min": 100, "max": 600}, {"min": 10, "max": 500}]:
            with self.subTest(bad=bad), self.assertRaises(LLMParseError):
                validate_llm_output(ok | {"pressure_range": bad}, q)

    def test_pressure_range_shape_rejections(self):
        q = "salinity between 100 and 500 dbar in 2023"
        for pr in [{"min": 100}, {"min": 100, "max": 500, "unit": "m"}, [100, 500],
                   {"min": None, "max": None}, {"min": 500, "max": 100},
                   {"min": -5, "max": 500}, {"min": "100", "max": 500},
                   {"min": float("inf"), "max": None}]:
            with self.subTest(pr=pr), self.assertRaises(LLMParseError):
                validate_llm_output(good(variable="salinity", month=None, pressure_range=pr), q)

    def test_pressure_surface_without_literal_rejected(self):
        # "surface" -> 0..50 is a rules-parser inference, not a literal; LLM must not invent it.
        with self.assertRaises(LLMParseError):
            validate_llm_output(good(pressure_range={"min": 0, "max": 50}, month=None),
                                "surface temperature in 2023")

    def test_decimal_and_thousands_pressure(self):
        q = "temperature deeper than 1,000 dbar in 2023"
        validate_llm_output(good(month=None, pressure_range={"min": 1000, "max": None}), q)
        with self.assertRaises(LLMParseError):
            validate_llm_output(good(month=None, pressure_range={"min": 1, "max": None}), q)

    def test_kind_consistency(self):
        with self.assertRaises(LLMParseError):   # knowledge without concept task
            validate_llm_output(good(question_kind="knowledge"), "what is salinity")
        with self.assertRaises(LLMParseError):   # data with concept task
            validate_llm_output(good(task="concept", year=None, month=None), "what is salinity")
        with self.assertRaises(LLMParseError):   # off_topic carrying data
            validate_llm_output(good(question_kind="off_topic"), "pizza recipe")
        with self.assertRaises(LLMParseError):   # null task on data
            validate_llm_output(good(task=None), Q)
        with self.assertRaises(LLMParseError):   # data with nothing actionable
            validate_llm_output(good(variable=None, year=None, month=None, stat="none"), "hello")

    def test_off_topic_and_knowledge_accepted(self):
        off = good(task=None, variable=None, stat="none", year=None, month=None,
                   question_kind="off_topic")
        validate_llm_output(off, "what is the capital of France")
        kn = good(task="concept", variable=None, stat="none", year=None, month=None,
                  question_kind="knowledge")
        validate_llm_output(kn, "what is a thermocline")


class TestParseQuestion(unittest.TestCase):
    def test_llm_success(self):
        intent = parse_question(Q, llm_call=fake(good()))
        self.assertEqual(intent["parser_used"], "llm")
        self.assertEqual(intent["question_kind"], "data")
        self.assertEqual((intent["variable"], intent["stat"], intent["year"], intent["month"]),
                         ("temperature", "avg", 2023, 1))
        self.assertEqual(intent["year_end"], 2023)

    def test_same_keys_as_rule_parser(self):
        rules = rule_intent.parse_intent(Q)
        intent = parse_question(Q, llm_call=fake(good()))
        self.assertEqual(set(intent) - {"parser_used", "question_kind"}, set(rules))

    def test_matches_rules_on_simple_query(self):
        rules = rule_intent.parse_intent(Q)
        intent = parse_question(Q, llm_call=fake(good(chart_type="none")))
        for k in ("task", "variable", "stat", "year", "month", "year_end", "month_end",
                  "platform_id", "named_region", "pressure_min", "pressure_max"):
            self.assertEqual(intent[k], rules[k], k)

    def test_llm_pressure_region_platform_mapping(self):
        q = "Average salinity in Andaman Sea between 100 and 500 dbar for float 2902758 in 2023"
        payload = good(variable="salinity", month=None, platform_id="2902758",
                       pressure_range={"min": 100, "max": 500}, region="Andaman Sea")
        intent = parse_question(q, llm_call=fake(payload))
        self.assertEqual(intent["parser_used"], "llm")
        self.assertEqual((intent["pressure_min"], intent["pressure_max"]), (100.0, 500.0))
        self.assertEqual(intent["named_region"], "Andaman Sea")
        self.assertEqual(intent["platform_id"], "2902758")

    def test_rule_only_fields_do_not_leak_into_llm_result(self):
        # Rules would find "Bay of Bengal" and 2023; the LLM said null -> stays null.
        q = "temperature in Bay of Bengal 2023"
        payload = good(year=None, month=None, region=None, stat="none")
        intent = parse_question(q, llm_call=fake(payload))
        self.assertEqual(intent["parser_used"], "llm")
        self.assertIsNone(intent["named_region"])
        self.assertIsNone(intent["year"])

    def test_export_and_profile_id_preserved(self):
        q = "export csv of temperature for profile 2902758_139 in 2023"
        payload = good(month=None, platform_id="2902758", task="float_detail")
        intent = parse_question(q, llm_call=fake(payload))
        self.assertTrue(intent["export_csv"])
        self.assertEqual(intent["profile_id"], "2902758_139")

    def test_knowledge_mapping(self):
        payload = good(task="concept", variable=None, stat="none", year=None, month=None,
                       question_kind="knowledge")
        intent = parse_question("What is a thermocline?", llm_call=fake(payload))
        self.assertEqual(intent["parser_used"], "llm")
        self.assertEqual(intent["task"], "concept")
        self.assertTrue(intent["is_conceptual"])
        self.assertFalse(intent["ambiguous"])

    def test_off_topic_mapping(self):
        payload = good(task=None, variable=None, stat="none", year=None, month=None,
                       question_kind="off_topic")
        intent = parse_question("Who won the cricket match?", llm_call=fake(payload))
        self.assertEqual(intent["parser_used"], "llm")
        self.assertEqual(intent["question_kind"], "off_topic")
        self.assertTrue(intent["ambiguous"])
        self.assertTrue(intent["clarification_needed"])

    def test_fallback_on_exception(self):
        def boom(prompt):
            raise RuntimeError("network down")
        intent = parse_question(Q, llm_call=boom)
        self.assertEqual(intent["parser_used"], "rules")
        self.assertEqual(intent["year"], 2023)

    def test_fallback_on_bad_json_hallucination_and_none(self):
        for call in [fake("not json"), fake(good(year=2020)), fake(good(stat="median")),
                     lambda p: None, fake({**good(), "extra": 1})]:
            intent = parse_question(Q, llm_call=call)
            self.assertEqual(intent["parser_used"], "rules")
            self.assertEqual(intent["variable"], "temperature")
            self.assertEqual(intent["year"], 2023)

    def test_whole_result_rejected_on_single_hallucination(self):
        # Everything valid except platform_id -> nothing from the LLM is kept.
        payload = good(platform_id="2902758", variable="salinity")
        intent = parse_question(Q, llm_call=fake(payload))
        self.assertEqual(intent["parser_used"], "rules")
        self.assertEqual(intent["variable"], "temperature")
        self.assertIsNone(intent["platform_id"])

    def test_fallback_when_gemini_unavailable(self):
        with patch.object(nl_parser.gemini_service, "is_gemini_available", return_value=False), \
             patch.object(nl_parser.gemini_service, "_call_gemini") as call:
            intent = parse_question(Q)
        call.assert_not_called()
        self.assertEqual(intent["parser_used"], "rules")

    def test_default_uses_gemini_service_when_available(self):
        with patch.object(nl_parser.gemini_service, "is_gemini_available", return_value=True), \
             patch.object(nl_parser.gemini_service, "_call_gemini",
                          return_value=json.dumps(good())) as call:
            intent = parse_question(Q)
        call.assert_called_once()
        self.assertEqual(intent["parser_used"], "llm")

    def test_empty_and_overlong_question_use_rules(self):
        called = []
        def spy(p):
            called.append(p); return json.dumps(good())
        for q in ["", "   ", "x" * 5000]:
            self.assertEqual(parse_question(q, llm_call=spy)["parser_used"], "rules")
        self.assertEqual(called, [])

    def test_rules_fallback_kind_and_history_passthrough(self):
        intent = parse_question("What is a thermocline?", llm_call=lambda p: None)
        self.assertEqual((intent["parser_used"], intent["question_kind"]), ("rules", "knowledge"))
        hist = [{"intent": {"variable": "temperature", "stat": "avg", "year": 2023}}]
        intent = parse_question("what about salinity?", history=hist, llm_call=lambda p: None)
        self.assertEqual((intent["variable"], intent["year"]), ("salinity", 2023))

    def test_input_history_not_mutated(self):
        hist = [{"intent": {"variable": "temperature", "year": 2023}}]
        snap = copy.deepcopy(hist)
        parse_question("what about salinity?", history=hist, llm_call=fake(good()))
        self.assertEqual(hist, snap)

    def test_prompt_contains_allowlists_and_no_secret(self):
        p = nl_parser.build_prompt(Q)
        for needle in ["discover_floats", "salinity", "floats_map", "Andaman Sea", "off_topic", Q]:
            self.assertIn(needle, p)
        self.assertNotIn("API_KEY", p)


class TestConfigConsistency(unittest.TestCase):
    def test_rule_parser_regions_are_allowlisted(self):
        samples = ["andaman", "north bay of bengal", "south bay of bengal",
                   "central bay of bengal", "bay of bengal", "sri lanka"]
        found = {rule_intent._extract_named_region(s) for s in samples}
        self.assertEqual(found, set(ALLOWED_REGIONS))


if __name__ == "__main__":
    unittest.main()
