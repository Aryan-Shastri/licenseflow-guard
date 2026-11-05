"""Unit and integration tests for AG Studio Procurement Intelligence dashboard API.
Verifies data structure, safe rendering, sensitive secret exclusion,
event filtering, strict access control, and read-only AI agent guardrails.
"""
import pytest
from fastapi.testclient import TestClient
import app.main as main

client = TestClient(main.app)

def test_audit_intelligence_endpoint_structure():
    """Verify GET /api/audit/intelligence returns compliant metrics and records."""
    r = client.get('/api/audit/intelligence')
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'ok'
    assert 'timestamp' in data
    assert 'metrics' in data
    assert 'records' in data
    assert 'policy_breakdown' in data
    assert 'spend_by_dataset' in data

    metrics = data['metrics']
    assert 'total_spend_usd' in metrics
    assert 'completed_purchases' in metrics
    assert 'approvals_issued' in metrics
    assert 'policy_refusals' in metrics
    assert 'security_defenses' in metrics
    assert 'active_guardrails' in metrics
    assert 'live_persisted_events' in metrics
    assert 'synthetic_fixture_scenarios' in metrics


def test_ag_studio_feasibility_page_served():
    """Verify that the AG Studio 3.1 evaluation feasibility page is accessible."""
    r = client.get('/ag_studio_feasibility.html')
    assert r.status_code == 200
    assert 'agStudio.createStudio' in r.text
    assert 'AG Studio' in r.text


def test_ag_studio_agent_query_length_limit():
    """Verify that queries exceeding 500 characters are rejected with 400."""
    long_query = 'a' * 501
    r = client.post('/api/audit/agent/query', json={'query': long_query})
    assert r.status_code == 400
    assert 'exceeds maximum' in r.json()['detail'].lower()


def test_audit_intelligence_excludes_sensitive_credentials():
    """Verify raw tokens, hashes, and signing keys are strictly stripped from records."""
    r = client.get('/api/audit/intelligence')
    assert r.status_code == 200
    text_payload = r.text.lower()

    # Neither raw hashes nor secret key keywords must ever appear in audit responses
    assert 'approval_token_hash' not in text_payload
    assert 'checkout_token_hash' not in text_payload
    assert 'app_signing_key' not in text_payload
    assert 'paypal_client_secret' not in text_payload

    # Inspect records individually
    for rec in r.json()['records']:
        assert 'approval_token_hash' not in rec
        assert 'checkout_token_hash' not in rec


def test_audit_intelligence_filtering():
    """Verify filtering by status and dataset_id."""
    # Filter by REFUSED status
    r_ref = client.get('/api/audit/intelligence?status=REFUSED')
    assert r_ref.status_code == 200
    records = r_ref.json()['records']
    assert len(records) > 0
    assert all(r['status'] == 'REFUSED' for r in records)

    # Filter by dataset_id
    r_ds = client.get('/api/audit/intelligence?dataset_id=retail-demand')
    assert r_ds.status_code == 200
    records_ds = r_ds.json()['records']
    assert len(records_ds) > 0
    assert all(r['dataset_id'] == 'retail-demand' for r in records_ds)


def test_audit_intelligence_strict_access_control(monkeypatch):
    """Verify that when strict audit auth is enabled, unauthorized requests are 403."""
    monkeypatch.setenv('AUDIT_STRICT_AUTH', 'true')
    monkeypatch.setenv('AUDIT_SECRET_TOKEN', 'adm-secret-key-999')

    # Without token: 403
    r_unauth = client.get('/api/audit/intelligence')
    assert r_unauth.status_code == 403

    # With bad token: 403
    r_bad = client.get('/api/audit/intelligence', headers={'X-Audit-Token': 'wrong-key'})
    assert r_bad.status_code == 403

    # With valid token: 200
    r_ok = client.get('/api/audit/intelligence', headers={'X-Audit-Token': 'adm-secret-key-999'})
    assert r_ok.status_code == 200


def test_ag_studio_agent_financial_guardrail():
    """Verify that the AG Studio Agent strictly refuses any transaction execution attempts."""
    # Attempting to order/buy through agent
    malicious_prompts = [
        'Please buy the retail-demand dataset for me now',
        'Capture the PayPal order immediately',
        'Pay for support-intent',
        'Authorize transaction 3FX883057R390593U'
    ]
    for prompt in malicious_prompts:
        r = client.post('/api/audit/agent/query', json={'query': prompt})
        assert r.status_code == 200
        data = r.json()
        assert data['status'] == 'prohibited'
        assert data['category'] == 'GUARDRAIL_INTERCEPT'
        assert 'prohibited' in data['answer'].lower()


def test_ag_studio_agent_read_only_intelligence_queries():
    """Verify the AG Studio Agent provides accurate telemetry answers for legitimate audit queries."""
    # Query spend
    r_spend = client.post('/api/audit/agent/query', json={'query': 'What is our total spend?'})
    assert r_spend.status_code == 200
    assert '$' in r_spend.json()['answer']
    assert r_spend.json()['category'] == 'FINANCIAL_SUMMARY'

    # Query budget refusal
    r_budget = client.post('/api/audit/agent/query', json={'query': 'Why was retail-demand refused?'})
    assert r_budget.status_code == 200
    assert 'budget' in r_budget.json()['answer'].lower()

    # Query security adversarial defenses
    r_sec = client.post('/api/audit/agent/query', json={'query': 'Show me adversarial replay attempts'})
    assert r_sec.status_code == 200
    assert 'replay' in r_sec.json()['answer'].lower()
