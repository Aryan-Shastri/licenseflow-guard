"""PayPal sandbox-only checkout. No production endpoint is configurable."""
import base64
import os
import httpx
from fastapi import HTTPException

API='https://api-m.sandbox.paypal.com'

def configured():
    return bool(os.getenv('PAYPAL_CLIENT_ID') and os.getenv('PAYPAL_CLIENT_SECRET'))

async def _token(client):
    cid=os.getenv('PAYPAL_CLIENT_ID',''); secret=os.getenv('PAYPAL_CLIENT_SECRET','')
    if not (cid and secret):
        raise HTTPException(503,'PayPal sandbox credentials have not been configured')
    basic=base64.b64encode(f'{cid}:{secret}'.encode()).decode()
    try:
        r=await client.post(f'{API}/v1/oauth2/token',data={'grant_type':'client_credentials'},
                            headers={'Authorization':f'Basic {basic}','Accept':'application/json'})
        r.raise_for_status()
        return r.json()['access_token']
    except (httpx.HTTPError,KeyError,ValueError):
        raise HTTPException(502,'PayPal sandbox authentication failed')

async def create_order(purchase_id, item):
    async with httpx.AsyncClient(timeout=20.0) as client:
        token=await _token(client)
        payload={'intent':'CAPTURE','purchase_units':[{'reference_id':purchase_id,
                'description':f'Demo licensed dataset: {item["name"]}',
                'amount':{'currency_code':'USD','value':item['price']}}]}
        try:
            r=await client.post(f'{API}/v2/checkout/orders',json=payload,
                                headers={'Authorization':f'Bearer {token}', 'Content-Type':'application/json',
                                         'PayPal-Request-Id':purchase_id[:36]})
            r.raise_for_status()
            return r.json()['id']
        except (httpx.HTTPError,ValueError,KeyError):
            raise HTTPException(502,'PayPal sandbox order creation failed')

async def capture_order(purchase_id, order_id):
    async with httpx.AsyncClient(timeout=20.0) as client:
        token=await _token(client)
        try:
            r=await client.post(f'{API}/v2/checkout/orders/{order_id}/capture',json={},
                                headers={'Authorization':f'Bearer {token}', 'Content-Type':'application/json',
                                         'PayPal-Request-Id':f'capture-{purchase_id[:28]}'})
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError,ValueError):
            raise HTTPException(502,'PayPal sandbox capture failed; verify status before retrying')


def capture_verified(capture_response, purchase_id, item):
    try:
        if capture_response['status']!='COMPLETED': return None
        unit=capture_response['purchase_units'][0]
        if unit['reference_id']!=purchase_id: return None
        record=unit['payments']['captures'][0]
        if record['status']!='COMPLETED': return None
        if record['amount']['currency_code']!='USD' or record['amount']['value']!=item['price']: return None
        return record['id']
    except (KeyError,IndexError,TypeError):
        return None
