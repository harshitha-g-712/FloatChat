"""Small deterministic smoke evaluation for FloatChat's local API."""
from fastapi.testclient import TestClient
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from main import app

CASES = [
    ("Average salinity in March 2023", "salinity"),
    ("Average oxygen in January 2023", "oxygen measurements"),
    ("How many floats are there?", "floats"),
    ("month 13", "invalid"),
]

def main():
    client = TestClient(app)
    failures = []
    for i, (question, expected) in enumerate(CASES):
        response = client.post("/api/chat", json={"message": question, "conversation_id": f"eval-{i}"})
        body = response.json()
        text = body.get("answer", "").lower()
        if response.status_code != 200 or expected not in text:
            failures.append((question, response.status_code, body.get("answer", "")))
    if failures:
        for item in failures:
            print("FAIL:", item)
        raise SystemExit(1)
    print(f"PASS: {len(CASES)} smoke evaluation cases")

if __name__ == "__main__":
    main()
