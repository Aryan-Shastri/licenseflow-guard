from fastapi.testclient import TestClient
import app.main as main

client=TestClient(main.app)

GOOD={'goal':'I need data for commercial customer-support model training', 'max_budget':35,
      'commercial':True,'training':True,'redistribution':False}


def test_health_and_catalog():
    assert client.get('/api/health').json()['sandbox_only'] is True
    assert len(client.get('/api/catalog').json()['items'])==4
    assert client.get('/').status_code==200


def test_permission_gate():
    r=client.post('/api/eligibility',json=GOOD)
    assert r.status_code==200
    assert r.json()['results']['support-intent']['eligible']
    assert not r.json()['results']['civic-dialogue']['eligible']


def test_quote_generation_and_validation(monkeypatch,tmp_path):
    monkeypatch.setattr(main,'DB',tmp_path/'orders.sqlite3')
    main.setup()
    # Ineligible dataset quote must be rejected by policy
    ineligible_req={'dataset_id':'civic-dialogue','intent':GOOD}
    assert client.post('/api/quotes',json=ineligible_req).status_code==422
    # Eligible dataset produces bound quote
    r=client.post('/api/quotes',json={'dataset_id':'support-intent','intent':GOOD})
    assert r.status_code==200
    data=r.json()
    assert data['dataset_id']=='support-intent'
    assert data['price_usd']=='24.00'
    assert data['currency']=='USD'
    assert 'approval_token' in data
    assert 'quote_id' in data


def test_unconfigured_payment_does_not_fabricate_success(monkeypatch,tmp_path):
    monkeypatch.setattr(main,'DB',tmp_path/'orders.sqlite3')
    main.setup()
    monkeypatch.setenv('PAYPAL_CLIENT_ID','')
    monkeypatch.setenv('PAYPAL_CLIENT_SECRET','')
    q=client.post('/api/quotes',json={'dataset_id':'support-intent','intent':GOOD}).json()
    r=client.post('/api/purchases',json={'dataset_id':'support-intent','intent':GOOD,
                                         'quote_id':q['quote_id'],'approval_token':q['approval_token']})
    assert r.status_code==503


def test_purchase_requires_server_approval(monkeypatch,tmp_path):
    monkeypatch.setattr(main,'DB',tmp_path/'orders.sqlite3')
    main.setup()
    monkeypatch.setattr(main.paypal,'configured',lambda:True)
    # Attempting purchase with fake/non-existent quote
    r=client.post('/api/purchases',json={'dataset_id':'support-intent','intent':GOOD,
                                         'quote_id':'fake-quote-id','approval_token':'fake-token'})
    assert r.status_code==403


def test_approval_replay_prevention(monkeypatch,tmp_path):
    monkeypatch.setattr(main,'DB',tmp_path/'orders.sqlite3')
    main.setup()
    monkeypatch.setattr(main.paypal,'configured',lambda:True)
    async def create_order(pid,item): return 'PAYPAL-SANDBOX-ORDER-1'
    monkeypatch.setattr(main.paypal,'create_order',create_order)

    q=client.post('/api/quotes',json={'dataset_id':'support-intent','intent':GOOD}).json()
    req={'dataset_id':'support-intent','intent':GOOD,'quote_id':q['quote_id'],'approval_token':q['approval_token']}
    # First purchase succeeds
    r1=client.post('/api/purchases',json=req)
    assert r1.status_code==200
    # Second attempt with same approval token is blocked as a replay attempt
    r2=client.post('/api/purchases',json=req)
    assert r2.status_code==409
    assert 'already been used' in r2.json()['detail']


def test_approval_tampering_rejected(monkeypatch,tmp_path):
    monkeypatch.setattr(main,'DB',tmp_path/'orders.sqlite3')
    main.setup()
    monkeypatch.setattr(main.paypal,'configured',lambda:True)
    # Get quote for support-intent ($24)
    q=client.post('/api/quotes',json={'dataset_id':'support-intent','intent':GOOD}).json()
    # Attempt to use that quote for safe-security ($34)
    tampered_req={'dataset_id':'safe-security','intent':GOOD,'quote_id':q['quote_id'],'approval_token':q['approval_token']}
    r=client.post('/api/purchases',json=tampered_req)
    assert r.status_code==422
    assert 'mismatch' in r.json()['detail'].lower()


def test_purchase_capture_receipt(monkeypatch,tmp_path):
    monkeypatch.setattr(main,'DB',tmp_path/'orders.sqlite3')
    main.setup()
    monkeypatch.setattr(main.paypal,'configured',lambda:True)
    async def create_order(pid,item): return 'PAYPAL-SANDBOX-ORDER'
    async def capture_order(pid,order_id):
        return {'status':'COMPLETED','purchase_units':[{'reference_id':pid,
                'payments':{'captures':[{'id':'TEST-CAPTURE','status':'COMPLETED','amount':{'currency_code':'USD','value':'24.00'}}]}}]}
    monkeypatch.setattr(main.paypal,'create_order',create_order)
    monkeypatch.setattr(main.paypal,'capture_order',capture_order)

    q=client.post('/api/quotes',json={'dataset_id':'support-intent','intent':GOOD}).json()
    r=client.post('/api/purchases',json={'dataset_id':'support-intent','intent':GOOD,
                                         'quote_id':q['quote_id'],'approval_token':q['approval_token']})
    assert r.status_code==200,r.text
    pid=r.json()['purchase_id']
    token_header={'X-Checkout-Token':r.json()['checkout_token']}
    assert client.post(f'/api/purchases/{pid}/capture').status_code==403
    assert client.get(f'/api/purchases/{pid}/receipt').status_code==403
    response=client.post(f'/api/purchases/{pid}/capture',headers=token_header)
    assert response.status_code==200,response.text
    token=response.json()['access_token'];header={'Authorization':f'Bearer {token}'}
    receipt=client.get(f'/api/purchases/{pid}/receipt',headers=header)
    assert receipt.status_code==200 and receipt.json()['paypal_capture_id']=='TEST-CAPTURE'
    assert receipt.json()['price_usd']=='24.00'
    assert receipt.json()['currency']=='USD'
    assert client.get(f'/api/purchases/{pid}/download',headers=header).status_code==200
    assert client.get(f'/api/purchases/{pid}/download',headers={'Authorization':'Bearer bogus'}).status_code==403
    # Subsequent capture returns cached completed capture
    assert client.post(f'/api/purchases/{pid}/capture',headers=token_header).json()['access_token']==token


def test_ai_matching_untrusted_output_filtered(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','mock-key')
    # Mock ai._rank to return both an allowed dataset and a forbidden/ineligible dataset
    def fake_rank(goal, eligible):
        from app.ai import MatchOutput, Choice
        return MatchOutput(
            rationale='Synthetic test advice',
            choices=[
                Choice(dataset_id='support-intent', explanation='Good match', limitation='Small sample size'),
                Choice(dataset_id='civic-dialogue', explanation='Commercial prohibited', limitation='Not for commercial')
            ]
        )
    monkeypatch.setattr(main.ai,'_rank',fake_rank)
    r=client.post('/api/match',json=GOOD)
    assert r.status_code==200
    data=r.json()
    assert data['model_used'] is True
    # civic-dialogue is NOT eligible under GOOD intent, so it must be filtered out!
    chosen_ids=[c['dataset_id'] for c in data['choices']]
    assert 'support-intent' in chosen_ids
    assert 'civic-dialogue' not in chosen_ids
