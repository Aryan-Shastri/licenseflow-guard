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


def test_unconfigured_payment_does_not_fabricate_success(monkeypatch):
    monkeypatch.setenv('PAYPAL_CLIENT_ID','')
    monkeypatch.setenv('PAYPAL_CLIENT_SECRET','')
    r=client.post('/api/purchases',json={'dataset_id':'support-intent','intent':GOOD})
    assert r.status_code==503


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
    r=client.post('/api/purchases',json={'dataset_id':'support-intent','intent':GOOD})
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
    assert client.get(f'/api/purchases/{pid}/download',headers=header).status_code==200
    assert client.get(f'/api/purchases/{pid}/download',headers={'Authorization':'Bearer bogus'}).status_code==403
    assert client.post(f'/api/purchases/{pid}/capture',headers=token_header).json()['access_token']==token
