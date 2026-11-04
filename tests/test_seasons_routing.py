"""
FloatChat – season coverage, classification, routing, float filter and chart hint
tests. Offline: Gemini is always a fake callable; DB is a seeded temp SQLite file.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND)

from retrieval import nl_parser
from retrieval.discovery import trajectory_points
from retrieval.nl_parser import parse_question
from retrieval.query_engine import build_query, retrieve
from retrieval.routing import route_intent
from retrieval.seasons import season_coverage
from retrieval.validators import validate_platform_id, validated_chart_hint


def good(**over):
    base = {"task": "stat", "variable": "temperature", "stat": "avg", "year": 2023,
            "month": 1, "platform_id": None, "pressure_range": None, "region": None,
            "chart_type": "none", "question_kind": "data"}
    base.update(over)
    return base


def fake(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return MagicMock(side_effect=lambda prompt: raw)


def no_llm(prompt):
    return None  # forces the rules fallback


def seed_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE profiles (id TEXT PRIMARY KEY, platform TEXT, lat REAL, lon REAL, timestamp TEXT, region TEXT)")
    c.execute("CREATE TABLE measurements (profile_id TEXT, pressure REAL, temperature REAL, salinity REAL)")
    profs = [("2902758_1", "2902758", 10.0, 85.0, "2023-03-05", "Bay of Bengal"),
             ("2902758_2", "2902758", 10.5, 85.5, "2023-06-10", "Bay of Bengal"),
             ("2902999_1", "2902999", 12.0, 88.0, "2023-04-02", "Bay of Bengal")]
    c.executemany("INSERT INTO profiles VALUES (?,?,?,?,?,?)", profs)
    c.executemany("INSERT INTO measurements VALUES (?,?,?,?)",
                  [(p[0], 10.0, 28.0, 33.0) for p in profs])
    c.commit()
    c.close()
    return path


class TestParserCore(unittest.TestCase):
    Q = "What was the average temperature in January 2023?"

    def test_valid_gemini_json_gives_llm_intent(self):
        llm = fake(good())
        intent = parse_question(self.Q, llm_call=llm)
        llm.assert_called_once()
        self.assertEqual(intent["parser_used"], "llm")
        self.assertEqual((intent["variable"], intent["stat"], intent["year"], intent["month"]),
                         ("temperature", "avg", 2023, 1))

    def test_hallucinated_year_uses_rules(self):
        intent = parse_question(self.Q, llm_call=fake(good(year=2020)))
        self.assertEqual(intent["parser_used"], "rules")
        self.assertEqual(intent["year"], 2023)

    def test_hallucinated_float_id_uses_rules(self):
        intent = parse_question(self.Q, llm_call=fake(good(platform_id="2902758")))
        self.assertEqual(intent["parser_used"], "rules")
        self.assertIsNone(intent["platform_id"])

    def test_gemini_failure_uses_rules(self):
        def boom(prompt):
            raise RuntimeError("API down")
        intent = parse_question(self.Q, llm_call=boom)
        self.assertEqual(intent["parser_used"], "rules")
        self.assertEqual(intent["variable"], "temperature")

    def test_invalid_json_and_allowlist_values_handled_safely(self):
        for call in [fake("not json"), fake("```json\n{broken\n```"), fake(good(chart_type="pie")),
                     fake(good(task="drop_table")), fake(good(region="Atlantis")),
                     fake({**good(), "sql": "DROP TABLE profiles"})]:
            intent = parse_question(self.Q, llm_call=call)
            self.assertEqual(intent["parser_used"], "rules")
            self.assertIn(intent["chart_type"], nl_parser.ALLOWED_CHART_TYPES)


class TestClassification(unittest.TestCase):
    OFF = "What is the capital of France?"
    KNOW = "Why is the Bay of Bengal fresher at the surface?"

    def test_off_topic_via_llm_does_not_retrieve(self):
        payload = good(task=None, variable=None, stat="none", year=None, month=None,
                       question_kind="off_topic")
        intent = parse_question(self.OFF, llm_call=fake(payload))
        retrieve_fn, traj_fn = MagicMock(), MagicMock()
        res = route_intent(intent, self.OFF, retrieve_fn=retrieve_fn, trajectory_fn=traj_fn)
        self.assertEqual((intent["question_kind"], res["route"]), ("off_topic", "off_topic"))
        self.assertIn("Sorry", res["answer"])
        retrieve_fn.assert_not_called()
        traj_fn.assert_not_called()

    def test_off_topic_rules_fallback(self):
        for q in [self.OFF, "Who won the cricket match?", "Tell me a joke"]:
            with self.subTest(q=q):
                intent = parse_question(q, llm_call=no_llm)
                self.assertEqual((intent["parser_used"], intent["question_kind"]), ("rules", "off_topic"))
                retrieve_fn = MagicMock()
                res = route_intent(intent, q, retrieve_fn=retrieve_fn)
                self.assertEqual(res["route"], "off_topic")
                self.assertFalse(res["retrieval_performed"])
                retrieve_fn.assert_not_called()

    def test_knowledge_kept_out_of_retrieval(self):
        # Rules fallback path (Gemini unavailable) and LLM path both stay out.
        llm_payload = good(task="concept", variable=None, stat="none", year=None, month=None,
                           region="Bay of Bengal", question_kind="knowledge")
        for call in [no_llm, fake(llm_payload)]:
            intent = parse_question(self.KNOW, llm_call=call)
            self.assertEqual(intent["question_kind"], "knowledge")
            self.assertEqual(intent["task"], "concept")
            retrieve_fn, traj_fn = MagicMock(), MagicMock()
            res = route_intent(intent, self.KNOW, retrieve_fn=retrieve_fn, trajectory_fn=traj_fn)
            self.assertEqual(res["route"], "knowledge")
            self.assertFalse(res["retrieval_performed"])
            retrieve_fn.assert_not_called()
            traj_fn.assert_not_called()

    def test_knowledge_rules_examples(self):
        for q in ["What is a thermocline?", "Explain the mixed layer", "How do Argo floats work?"]:
            self.assertEqual(parse_question(q, llm_call=no_llm)["question_kind"], "knowledge", q)

    def test_data_questions_stay_data(self):
        for q in ["What was the average temperature in January 2023?",
                  "List floats in 2023", "Show temperature profile for float 2902758",
                  "Where did float 2902758 travel?", "Plot salinity in the Bay of Bengal"]:
            self.assertEqual(parse_question(q, llm_call=no_llm)["question_kind"], "data", q)


def _window(start, end):
    """Pin the dataset window the season logic sees (it is normally read from the database)."""
    return patch.multiple("retrieval.seasons", DATASET_START=start, DATASET_END=end)


class TestSeasons(unittest.TestCase):
    """Window January-June 2023: exercises partial / none coverage regardless of the loaded data."""

    def setUp(self):
        p = _window((2023, 1), (2023, 6))
        p.start()
        self.addCleanup(p.stop)

    def test_coverage_levels(self):
        sw = season_coverage("south_west_monsoon")
        self.assertEqual((sw["coverage"], sw["covered_months"]), ("partial", [[2023, 6]]))
        self.assertEqual(sw["missing_months"], [[2023, 7], [2023, 8], [2023, 9]])
        self.assertTrue(sw["partial_coverage"])
        self.assertIn("June 2023", sw["coverage_note"])
        self.assertIn("not represent the complete season", sw["coverage_note"])
        ne = season_coverage("north_east_monsoon")
        self.assertEqual((ne["coverage"], ne["covered_months"]), ("none", []))
        pre = season_coverage("pre_monsoon")
        self.assertEqual((pre["coverage"], pre["covered_months"]),
                         ("full", [[2023, 3], [2023, 4], [2023, 5]]))
        self.assertFalse(pre["partial_coverage"])

    def test_explicit_other_year_has_no_coverage(self):
        self.assertEqual(season_coverage("pre_monsoon", 2022)["coverage"], "none")

    def test_south_west_monsoon_query_is_partial_and_narrowed(self):
        for q in ["Average salinity during the south-west monsoon",
                  "average salinity in the southwest monsoon", "SW monsoon average salinity"]:
            intent = parse_question(q, llm_call=no_llm)
            self.assertEqual(intent["season"]["coverage"], "partial", q)
            # date filter limited to covered month only, never the full season
            self.assertEqual((intent["year"], intent["month"], intent["year_end"], intent["month_end"]),
                             (2023, 6, 2023, 6), q)

    def test_north_east_monsoon_has_no_data_and_no_retrieval(self):
        q = "Average temperature in the north-east monsoon"
        intent = parse_question(q, llm_call=no_llm)
        self.assertEqual(intent["season"]["coverage"], "none")
        self.assertTrue(intent["no_data_in_dataset"])
        self.assertIsNone(intent["year"])
        retrieve_fn = MagicMock()
        res = route_intent(intent, q, retrieve_fn=retrieve_fn)
        retrieve_fn.assert_not_called()
        self.assertIn("No data", res["answer"])

    def test_pre_monsoon_full_march_to_may(self):
        intent = parse_question("Average temperature in the pre-monsoon", llm_call=no_llm)
        self.assertEqual(intent["season"]["coverage"], "full")
        self.assertEqual((intent["year"], intent["month"], intent["year_end"], intent["month_end"]),
                         (2023, 3, 2023, 5))

    def test_season_applies_on_llm_path_and_routes_with_note(self):
        q = "Average salinity in the south-west monsoon"
        payload = good(variable="salinity", year=None, month=None, region=None)
        intent = parse_question(q, llm_call=fake(payload))
        self.assertEqual(intent["parser_used"], "llm")
        retrieve_fn = MagicMock(return_value={"count": 0, "rows": []})
        res = route_intent(intent, q, retrieve_fn=retrieve_fn)
        retrieve_fn.assert_called_once()
        self.assertTrue(res["partial_coverage"])
        self.assertIn("June 2023", res["answer_prefix"])

    def test_multiple_seasons_are_ambiguous(self):
        intent = parse_question("Compare salinity in the south-west and north-east monsoon",
                                llm_call=no_llm)
        self.assertTrue(intent["ambiguous"])
        self.assertEqual(len(intent["seasons"]), 2)

    def test_season_knowledge_question_not_treated_as_data(self):
        intent = parse_question("Why does the south-west monsoon freshen the Bay of Bengal?",
                                llm_call=no_llm)
        self.assertEqual(intent["question_kind"], "knowledge")
        self.assertNotIn("season", intent)


class TestFloatFilterAndChartHints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = seed_db()

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.db)

    def test_validators(self):
        self.assertEqual(validate_platform_id("2902758"), "2902758")
        for bad in [None, "", "123", "29027580", 2902758, "290275a", " 2902758", "2902758; DROP"]:
            self.assertIsNone(validate_platform_id(bad), bad)
        self.assertEqual(validated_chart_hint("trajectory"), "trajectory")
        for bad in ["none", "pie", None, 5]:
            self.assertIsNone(validated_chart_hint(bad), bad)

    def test_trajectory_filters_by_valid_float(self):
        pts = trajectory_points("2902758", db_path=self.db)
        self.assertEqual({p["platform"] for p in pts}, {"2902758"})
        self.assertEqual(len(pts), 2)

    def test_no_float_filter_without_valid_id(self):
        for bad in [None, "bogus", "123"]:
            pts = trajectory_points(bad, db_path=self.db)
            self.assertEqual({p["platform"] for p in pts}, {"2902758", "2902999"}, bad)

    def test_trajectory_date_filter(self):
        pts = trajectory_points("2902758", db_path=self.db, year=2023, month=6,
                                year_end=2023, month_end=6)
        self.assertEqual([p["profile_id"] for p in pts], ["2902758_2"])

    def test_query_engine_float_filter_validated(self):
        sql, params = build_query({"platform_id": "2902758"})
        self.assertIn("p.platform = ?", sql)
        self.assertIn("2902758", params)
        sql, params = build_query({"platform_id": "x'; DROP TABLE profiles;--"})
        self.assertNotIn("p.platform = ?", sql)
        self.assertEqual(params, [])
        res = retrieve({"variable": "temperature", "stat": "count", "platform_id": "2902758"},
                       db_path=self.db)
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["filters"]["platform_id"], "2902758")

    def test_route_trajectory_passes_float_and_chart_hint(self):
        q = "Where did float 2902758 travel?"
        payload = good(task="trajectory", variable=None, stat="none", year=None, month=None,
                       platform_id="2902758", chart_type="trajectory")
        intent = parse_question(q, llm_call=fake(payload))
        self.assertEqual(intent["parser_used"], "llm")
        traj_fn = MagicMock(return_value=[])
        res = route_intent(intent, q, trajectory_fn=traj_fn)
        self.assertEqual(traj_fn.call_args.args[0], "2902758")
        self.assertEqual((res["platform_filter"], res["chart_hint"], res["chart_type"]),
                         ("2902758", "trajectory", "trajectory"))

    def test_route_trajectory_end_to_end_with_db(self):
        q = "Where did float 2902758 travel?"
        intent = parse_question(q, llm_call=no_llm)
        res = route_intent(intent, q, db_path=self.db)
        self.assertEqual({p["platform"] for p in res["data"]}, {"2902758"})

    def test_route_without_valid_float_applies_no_filter(self):
        intent = {"question_kind": "data", "task": "trajectory", "platform_id": "12",
                  "chart_type": "none"}
        traj_fn = MagicMock(return_value=[])
        res = route_intent(intent, "", trajectory_fn=traj_fn)
        self.assertIsNone(traj_fn.call_args.args[0])
        self.assertIsNone(res["platform_filter"])

    def test_chart_hint_passed_and_allowlisted(self):
        q = "Show temperature distribution in 2023"
        intent = parse_question(q, llm_call=fake(good(month=None, stat="none",
                                                      chart_type="distribution")))
        res = route_intent(intent, q, retrieve_fn=MagicMock(return_value={}))
        self.assertEqual((res["chart_hint"], res["chart_type"]), ("distribution", "distribution"))
        # A tampered / unsupported hint never reaches the metadata.
        res = route_intent({**intent, "chart_type": "pie"}, q, retrieve_fn=MagicMock(return_value={}))
        self.assertIsNone(res["chart_hint"])


if __name__ == "__main__":
    unittest.main()


class TestSeasonsTwoYears(unittest.TestCase):
    """Window January 2023 - December 2024 (the data loaded by the default loader command)."""

    def setUp(self):
        p = _window((2023, 1), (2024, 12))
        p.start()
        self.addCleanup(p.stop)

    def _filter(self, intent):
        return (intent["year"], intent["month"], intent["year_end"], intent["month_end"])

    def test_without_a_year_the_first_year_is_used_and_other_years_are_named(self):
        intent = parse_question("Average salinity during the south-west monsoon", llm_call=no_llm)
        sw = intent["season"]
        self.assertEqual((sw["coverage"], sw["season_year"], sw["year_assumed"]), ("full", 2023, True))
        self.assertEqual(self._filter(intent), (2023, 6, 2023, 9))
        self.assertIn("2023 was assumed", sw["coverage_note"])
        self.assertIn("2024", sw["coverage_note"].split("assumed.)")[1])

    def test_explicit_second_year_is_used(self):
        intent = parse_question("Average salinity in the south-west monsoon 2024", llm_call=no_llm)
        self.assertEqual((intent["season"]["coverage"], intent["season"]["year_assumed"]), ("full", False))
        self.assertEqual(self._filter(intent), (2024, 6, 2024, 9))

    def test_pre_monsoon_2024_is_full(self):
        intent = parse_question("Average temperature in the pre-monsoon 2024", llm_call=no_llm)
        self.assertEqual(intent["season"]["coverage"], "full")
        self.assertEqual(self._filter(intent), (2024, 3, 2024, 5))

    def test_north_east_monsoon_2023_spans_into_2024(self):
        intent = parse_question("Average temperature in the north-east monsoon", llm_call=no_llm)
        self.assertEqual(intent["season"]["coverage"], "full")
        self.assertEqual(self._filter(intent), (2023, 10, 2024, 1))

    def test_north_east_monsoon_2024_is_partial_because_january_2025_is_missing(self):
        intent = parse_question("Average temperature in the north-east monsoon 2024", llm_call=no_llm)
        sw = intent["season"]
        self.assertEqual(sw["coverage"], "partial")
        self.assertEqual(sw["missing_months"], [[2025, 1]])
        self.assertEqual(self._filter(intent), (2024, 10, 2024, 12))
        retrieve_fn = MagicMock(return_value={"count": 0, "rows": []})
        res = route_intent(intent, "Average temperature in the north-east monsoon 2024", retrieve_fn=retrieve_fn)
        self.assertTrue(res["partial_coverage"])
        self.assertIn("January 2025", res["answer_prefix"])

    def test_years_outside_the_window_have_no_data_and_no_retrieval(self):
        for q in ("Average temperature in the pre-monsoon 2025", "Average temperature in the pre-monsoon 2022"):
            intent = parse_question(q, llm_call=no_llm)
            self.assertEqual(intent["season"]["coverage"], "none", q)
            self.assertTrue(intent["no_data_in_dataset"], q)
            retrieve_fn = MagicMock()
            route_intent(intent, q, retrieve_fn=retrieve_fn)
            retrieve_fn.assert_not_called()


class TestCoverageFollowsDatabase(unittest.TestCase):
    def test_config_window_equals_database_window(self):
        import config
        conn = sqlite3.connect(config.DB_PATH)
        try:
            lo, hi = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM profiles").fetchone()
        finally:
            conn.close()
        self.assertEqual(config.DATASET_START, (int(lo[:4]), int(lo[5:7])))
        self.assertEqual(config.DATASET_END, (int(hi[:4]), int(hi[5:7])))
