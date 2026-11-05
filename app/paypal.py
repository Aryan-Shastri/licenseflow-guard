"""PayPal sandbox-only checkout. No production endpoint is configurable."""
import asyncio
import base64
import os
import time
import httpx
from fastapi import HTTPException

API = 'https://api-m.sandbox.paypal.com'

_token_cache = {
    'token': None,
    'expires_at': 0.0,
    'cid': None
}
_token_lock: asyncio.Lock | None = None

def _get_lock() -> asyncio.Lock:
    global _token_lock
    if _token_lock is None:
        _token_lock = asyncio.Lock()
    return _token_lock

def configured() -> bool:
    return bool(os.getenv('PAYPAL_CLIENT_ID') and os.getenv('PAYPAL_CLIENT_SECRET'))

def clear_token_cache():
    """Clear in-memory cached OAuth2 access token."""
    _token_cache['token'] = None
    _token_cache['expires_at'] = 0.0
    _token_cache['cid'] = None

def _extract_error_detail(err: httpx.HTTPStatusError, fallback: str) -> str:
    try:
        data = err.response.json()
        name = data.get('name')
        msg = data.get('message')
        debug_id = data.get('debug_id')
        parts = []
        if name:
            parts.append(name)
        if msg:
            parts.append(msg)
        if debug_id:
            parts.append(f"(PayPal-Debug-Id: {debug_id})")
        if parts:
            return f"{fallback}: {' - '.join(parts)}"
    except Exception:
        pass
    return fallback

async def _token(client: httpx.AsyncClient) -> str:
    cid = os.getenv('PAYPAL_CLIENT_ID', '')
    secret = os.getenv('PAYPAL_CLIENT_SECRET', '')
    if not (cid and secret):
        raise HTTPException(503, 'PayPal sandbox credentials have not been configured')

    now = time.monotonic()
    if _token_cache['token'] and _token_cache['cid'] == cid and now < _token_cache['expires_at']:
        return _token_cache['token']

    lock = _get_lock()
    async with lock:
        now = time.monotonic()
        if _token_cache['token'] and _token_cache['cid'] == cid and now < _token_cache['expires_at']:
            return _token_cache['token']

        basic = base64.b64encode(f'{cid}:{secret}'.encode()).decode()
        try:
            r = await client.post(
                f'{API}/v1/oauth2/token',
                data={'grant_type': 'client_credentials'},
                headers={'Authorization': f'Basic {basic}', 'Accept': 'application/json'}
            )
            r.raise_for_status()
            payload = r.json()
            access_token = payload['access_token']
            expires_in = int(payload.get('expires_in', 3600))
            # Safety margin: renew 60 seconds before expiration
            margin = 60 if expires_in > 120 else 10
            _token_cache['token'] = access_token
            _token_cache['expires_at'] = time.monotonic() + max(30, expires_in - margin)
            _token_cache['cid'] = cid
            return access_token
        except httpx.HTTPStatusError as e:
            detail = _extract_error_detail(e, 'PayPal sandbox authentication failed')
            raise HTTPException(502, detail)
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(502, 'PayPal sandbox authentication failed')

async def create_order(purchase_id: str, item: dict) -> str:
    async with httpx.AsyncClient(timeout=20.0) as client:
        token = await _token(client)
        payload = {
            'intent': 'CAPTURE',
            'purchase_units': [{
                'reference_id': purchase_id,
                'description': f'Demo licensed dataset: {item["name"]}',
                'amount': {'currency_code': 'USD', 'value': item['price']}
            }]
        }
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Prefer': 'return=representation',
            'PayPal-Request-Id': purchase_id[:36]
        }
        try:
            r = await client.post(f'{API}/v2/checkout/orders', json=payload, headers=headers)
            r.raise_for_status()
            return r.json()['id']
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                clear_token_cache()
            detail = _extract_error_detail(e, 'PayPal sandbox order creation failed')
            raise HTTPException(502, detail)
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(502, 'PayPal sandbox order creation failed')

async def capture_order(purchase_id: str, order_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        token = await _token(client)
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Prefer': 'return=representation',
            'PayPal-Request-Id': f'capture-{purchase_id[:28]}'
        }
        try:
            r = await client.post(f'{API}/v2/checkout/orders/{order_id}/capture', json={}, headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                clear_token_cache()
            # If PayPal reported ORDER_ALREADY_CAPTURED, attempt reconciliation
            try:
                err_data = e.response.json()
                issues = [iss.get('issue') for iss in err_data.get('details', [])]
                if 'ORDER_ALREADY_CAPTURED' in issues:
                    reconciled = await get_order_details(order_id)
                    if reconciled.get('status') == 'COMPLETED':
                        return reconciled
            except Exception:
                pass
            detail = _extract_error_detail(e, 'PayPal sandbox capture failed; verify status before retrying')
            raise HTTPException(502, detail)
        except (httpx.TimeoutException, httpx.NetworkError):
            # Ambiguous network drop / timeout: reconcile read-only order status before failing
            try:
                reconciled = await get_order_details(order_id)
                if reconciled.get('status') == 'COMPLETED':
                    return reconciled
            except Exception:
                pass
            raise HTTPException(504, 'PayPal capture timed out and could not be verified; order status queried')
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, 'PayPal sandbox capture failed; verify status before retrying')

async def get_order_details(order_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        token = await _token(client)
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'Prefer': 'return=representation'
        }
        try:
            r = await client.get(f'{API}/v2/checkout/orders/{order_id}', headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                clear_token_cache()
            detail = _extract_error_detail(e, 'PayPal sandbox order status query failed')
            raise HTTPException(502, detail)
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, 'PayPal sandbox order status query failed')

def capture_verified(capture_response: dict, purchase_id: str, item: dict):
    try:
        if capture_response.get('status') != 'COMPLETED':
            return None
        units = capture_response.get('purchase_units', [])
        if not units:
            return None
        unit = units[0]
        if unit.get('reference_id') != purchase_id:
            return None
        payments = unit.get('payments', {})
        captures = payments.get('captures', [])
        if not captures:
            return None
        record = captures[0]
        if record.get('status') != 'COMPLETED':
            return None
        amount = record.get('amount', {})
        if amount.get('currency_code') != 'USD' or amount.get('value') != item['price']:
            return None
        return record.get('id')
    except (KeyError, IndexError, TypeError):
        return None
