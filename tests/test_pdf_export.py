"""Unit tests for the /api/export/pdf endpoint."""
import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from main import app, _RATE_LIMITS

client = TestClient(app)


def test_pdf_export_guest_conversation():
    _RATE_LIMITS.clear()
    conv_id = "test-pdf-conv-001"
    # 1. Ask a question first so export data exists
    chat_resp = client.post("/api/chat", json={
        "message": "What is the average temperature in January 2023?",
        "conversation_id": conv_id
    })
    assert chat_resp.status_code == 200

    # 2. Request PDF export
    pdf_resp = client.post("/api/export/pdf", json={
        "conversation_id": conv_id
    })
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in pdf_resp.headers["content-disposition"]
    assert "report_" in pdf_resp.headers["content-disposition"]
    # PDF magic bytes
    assert pdf_resp.content.startswith(b"%PDF")
    assert len(pdf_resp.content) > 1000

