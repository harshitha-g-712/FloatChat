"""API regression tests for the live FastAPI request path."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def ask(q, **kwargs):
    return client.post('/api/chat', json={'message': q, 'conversation_id': 'api-test-' + str(abs(hash(q))), **kwargs})

def test_unsupported_variable_never_substitutes_temperature():
    r = ask('Average oxygen in January 2023')
    assert r.status_code == 200
    assert 'does not contain oxygen measurements' in r.json()['answer']
    assert r.json().get('variable') is None

def test_salinity_variable_is_preserved():
    r = ask('How salty was the sea in March 2023')
    assert r.status_code == 200
    assert r.json()['variable'] == 'salinity'
    assert 'PSU' in r.json()['answer']

def test_float_count_is_not_observation_count():
    r = ask('How many floats are there?')
    assert r.status_code == 200
    assert 'floats with measurement records' in r.json()['answer']
    assert 'observations' not in r.json()['answer']

def test_invalid_month_is_not_ignored():
    r = ask('month 13')
    assert r.status_code == 200
    assert 'invalid' in r.json()['answer'].lower()

def test_parser_metadata_is_returned():
    r = ask('Average salinity in March 2023')
    assert r.status_code == 200
    assert r.json()['parser_used'] in {'rules', 'llm'}
