"""Helper for test_new_years.py: ask questions through the real /api/chat against DB_PATH and print JSON."""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)
out = {}
for i, q in enumerate(json.loads(sys.argv[1])):
    r = client.post("/api/chat", json={"message": q, "conversation_id": f"ny-{i}"})
    j = r.json()
    out[q] = {"status": r.status_code, **{k: j.get(k) for k in ("answer", "stat", "observation_count", "ambiguous", "interpreted_as", "chart_type", "discovery_data")}}
print("@@JSON@@" + json.dumps(out, default=str))
