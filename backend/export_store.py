"""Persistent CSV-export support for saved chats (no web framework imports).

Each saved assistant message may carry an ``export_data`` JSON string (stored in the
history database, NOT sent to the browser). It holds what a CSV export needs:

    {"v": 1, "task": "stat", "intent": {...}, "result": {...} | null, "truncated": bool}

* ``result`` is the full result dict (observation rows / discovery lists) when its compact
  JSON is within ``MAX_STORED_BYTES`` and ``MAX_STORED_ROWS``.
* Otherwise only the (small) validated ``intent`` is kept and ``resolve_result`` re-runs
  the same read-only query against the ocean database when the export is requested.
  Discovery results are always small, so they are never truncated in practice; if one
  ever exceeded the cap it simply cannot be exported after the cache expires.
* Only the newest export payload of a conversation is kept (older ones are cleared by
  ``auth.save_message``), so the history database grows by at most one capped payload
  per conversation.
"""
import csv
import io
import json
from typing import Any, Callable, Dict, Optional, Tuple

MAX_STORED_BYTES = 400_000
MAX_STORED_ROWS = 5_000
PAYLOAD_VERSION = 1

_DISCOVERY_KEYS = ("floats", "trajectory", "coverage", "float_summary", "similar_profiles")


def build_export_payload(task: str, intent: Dict[str, Any], result: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return the JSON string to store with an assistant message (or None if nothing to export)."""
    if not isinstance(result, dict):
        return None
    safe_intent = json.loads(json.dumps(intent or {}, default=str))
    payload: Dict[str, Any] = {"v": PAYLOAD_VERSION, "task": task, "intent": safe_intent,
                               "result": result, "truncated": False}
    text = json.dumps(payload, separators=(",", ":"), default=str)
    too_many_rows = isinstance(result.get("rows"), list) and len(result["rows"]) > MAX_STORED_ROWS
    if len(text.encode("utf-8")) <= MAX_STORED_BYTES and not too_many_rows:
        return text
    if task != "stat":
        return None  # cannot be re-derived from the intent alone; export falls back to 409
    payload["result"] = None
    payload["truncated"] = True
    return json.dumps(payload, separators=(",", ":"), default=str)


def resolve_result(stored_json: Optional[str], retrieve_fn: Callable[[dict], dict]) -> Optional[Dict[str, Any]]:
    """Turn a stored payload back into a result dict, re-running the query if rows were not kept."""
    if not stored_json:
        return None
    try:
        payload = json.loads(stored_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("result"), dict):
        return payload["result"]
    if payload.get("task") == "stat" and isinstance(payload.get("intent"), dict):
        return retrieve_fn(payload["intent"])
    return None


def csv_for_result(stored: Optional[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """Build (csv_text, filename) from a result dict, or None if it has nothing exportable."""
    if not stored:
        return None
    buf = io.StringIO()
    if isinstance(stored.get("floats"), list):
        w = csv.DictWriter(buf, fieldnames=["platform", "profile_count", "first_date", "last_date", "avg_max_depth"], extrasaction="ignore")
        w.writeheader(); w.writerows(stored["floats"])
        return buf.getvalue(), "floatchat_floats.csv"
    if isinstance(stored.get("trajectory"), list):
        w = csv.DictWriter(buf, fieldnames=["profile_id", "platform", "lat", "lon", "timestamp"], extrasaction="ignore")
        w.writeheader(); w.writerows(stored["trajectory"])
        return buf.getvalue(), "floatchat_trajectory.csv"
    if isinstance(stored.get("coverage"), dict):
        w = csv.DictWriter(buf, fieldnames=["metric", "value"])
        w.writeheader()
        for key, value in stored["coverage"].items():
            w.writerow({"metric": key, "value": json.dumps(value) if isinstance(value, (dict, list)) else value})
        return buf.getvalue(), "floatchat_coverage.csv"
    if isinstance(stored.get("float_summary"), dict):
        w = csv.DictWriter(buf, fieldnames=["field", "value"])
        w.writeheader()
        for key, value in (stored.get("float_summary") or {}).items():
            w.writerow({"field": key, "value": json.dumps(value) if isinstance(value, (dict, list)) else value})
        return buf.getvalue(), "floatchat_float_detail.csv"
    if isinstance(stored.get("similar_profiles"), list):
        rows = stored["similar_profiles"]
        fields = sorted({k for r in rows for k in r}) if rows else ["profile_id", "platform", "similarity_score"]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
        return buf.getvalue(), "floatchat_similar_profiles.csv"
    if isinstance(stored.get("rows"), list):
        w = csv.DictWriter(buf, fieldnames=["id", "platform", "lat", "lon", "timestamp", "pressure", "temperature", "salinity"], extrasaction="ignore")
        w.writeheader(); w.writerows(stored["rows"])
        return buf.getvalue(), "floatchat_observations.csv"
    return None
