"""Unit and resilience tests for PayPal sandbox integration hardening.
Verifies token caching, header adherence (Prefer: return=representation),
network drop reconciliation, and structured error reporting.
"""
import time
import pytest
import httpx
from fastapi import HTTPException
import app.paypal as paypal

@pytest.fixture(autouse=True)
def reset_paypal_state(monkeypatch):
    monkeypatch.setenv('PAYPAL_CLIENT_ID', 'test_client_id')
    monkeypatch.setenv('PAYPAL_CLIENT_SECRET', 'test_client_secret')
    paypal.clear_token_cache()
    yield
    paypal.clear_token_cache()


@pytest.mark.anyio
async def test_token_caching_and_expiration(monkeypatch):
    call_count = 0

    async def fake_post(self, url, *args, **kwargs):
        nonlocal call_count
        if '/v1/oauth2/token' in str(url):
            call_count += 1
            return httpx.Response(
                200,
                json={'access_token': f'fake-token-{call_count}', 'expires_in': 3600},
                request=httpx.Request('POST', url)
            )
        raise NotImplementedError(str(url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)

    async with httpx.AsyncClient() as client:
        # First call: fetches from API
        t1 = await paypal._token(client)
        assert t1 == 'fake-token-1'
        assert call_count == 1

        # Second call immediately after: uses cache, no HTTP call
        t2 = await paypal._token(client)
        assert t2 == 'fake-token-1'
        assert call_count == 1

        # Simulate token expiration
        paypal._token_cache['expires_at'] = time.monotonic() - 10

        # Third call: cache is expired, fetches new token
        t3 = await paypal._token(client)
        assert t3 == 'fake-token-2'
        assert call_count == 2


@pytest.mark.anyio
async def test_token_invalidation_on_401(monkeypatch):
    # Set cached token
    paypal._token_cache['token'] = 'old-expired-token'
    paypal._token_cache['expires_at'] = time.monotonic() + 1000
    paypal._token_cache['cid'] = 'test_client_id'

    async def fake_post(self, url, *args, **kwargs):
        req = httpx.Request('POST', url)
        # Mock 401 unauthorized
        return httpx.Response(
            401,
            json={'error': 'invalid_token', 'error_description': 'Token expired'},
            request=req
        )

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)

    with pytest.raises(HTTPException) as exc_info:
        await paypal.create_order('order-test-1', {'name': 'Test', 'price': '24.00'})
    assert exc_info.value.status_code == 502
    # Verify token cache was invalidated
    assert paypal._token_cache['token'] is None


@pytest.mark.anyio
async def test_orders_v2_headers_and_payload(monkeypatch):
    captured_requests = []

    async def fake_post(self, url, *args, **kwargs):
        req = httpx.Request('POST', url, headers=kwargs.get('headers'))
        captured_requests.append((str(url), kwargs.get('headers'), kwargs.get('json')))
        if '/v1/oauth2/token' in str(url):
            return httpx.Response(200, json={'access_token': 'mock-tok', 'expires_in': 3600}, request=req)
        if '/v2/checkout/orders' in str(url):
            return httpx.Response(201, json={'id': 'MOCK-ORDER-123', 'status': 'CREATED'}, request=req)
        raise NotImplementedError(str(url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)

    order_id = await paypal.create_order('purchase-abc-123', {'name': 'Support Intent', 'price': '24.00'})
    assert order_id == 'MOCK-ORDER-123'

    order_call = [c for c in captured_requests if '/v2/checkout/orders' in c[0]][0]
    headers = order_call[1]
    assert headers['Prefer'] == 'return=representation'
    assert headers['PayPal-Request-Id'] == 'purchase-abc-123'
    assert headers['Authorization'] == 'Bearer mock-tok'


@pytest.mark.anyio
async def test_capture_timeout_reconciliation_success(monkeypatch):
    """When capture times out, paypal.capture_order queries get_order_details and recovers completed state."""
    async def fake_post(self, url, *args, **kwargs):
        if '/v1/oauth2/token' in str(url):
            req = httpx.Request('POST', url)
            return httpx.Response(200, json={'access_token': 'mock-tok', 'expires_in': 3600}, request=req)
        if '/capture' in str(url):
            # Simulate network drop / timeout after PayPal already processed the capture
            raise httpx.TimeoutException('Connection timed out waiting for PayPal response')
        raise NotImplementedError(str(url))

    async def fake_get(self, url, *args, **kwargs):
        req = httpx.Request('GET', url)
        # Order reconciliation query confirms COMPLETED capture status
        return httpx.Response(200, json={
            'id': 'ORDER-RECONCILED',
            'status': 'COMPLETED',
            'purchase_units': [{
                'reference_id': 'purchase-rec-001',
                'payments': {
                    'captures': [{
                        'id': 'RECONCILED-CAP-999',
                        'status': 'COMPLETED',
                        'amount': {'currency_code': 'USD', 'value': '24.00'}
                    }]
                }
            }]
        }, request=req)

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)
    monkeypatch.setattr(httpx.AsyncClient, 'get', fake_get)

    result = await paypal.capture_order('purchase-rec-001', 'ORDER-RECONCILED')
    assert result['status'] == 'COMPLETED'
    # capture_verified should confirm the reconciled capture
    cap_id = paypal.capture_verified(result, 'purchase-rec-001', {'price': '24.00'})
    assert cap_id == 'RECONCILED-CAP-999'


@pytest.mark.anyio
async def test_capture_timeout_reconciliation_failure(monkeypatch):
    """When capture times out and get_order_details indicates order is still not completed, fail closed with 504."""
    async def fake_post(self, url, *args, **kwargs):
        if '/v1/oauth2/token' in str(url):
            req = httpx.Request('POST', url)
            return httpx.Response(200, json={'access_token': 'mock-tok', 'expires_in': 3600}, request=req)
        if '/capture' in str(url):
            raise httpx.TimeoutException('Connection timed out')
        raise NotImplementedError(str(url))

    async def fake_get(self, url, *args, **kwargs):
        req = httpx.Request('GET', url)
        # Order status remains APPROVED, not captured
        return httpx.Response(200, json={'id': 'ORDER-1', 'status': 'APPROVED'}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)
    monkeypatch.setattr(httpx.AsyncClient, 'get', fake_get)

    with pytest.raises(HTTPException) as exc_info:
        await paypal.capture_order('purchase-fail-001', 'ORDER-1')
    assert exc_info.value.status_code == 504
    assert 'timed out' in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_structured_error_extraction(monkeypatch):
    async def fake_post(self, url, *args, **kwargs):
        if '/v1/oauth2/token' in str(url):
            req = httpx.Request('POST', url)
            return httpx.Response(200, json={'access_token': 'mock-tok', 'expires_in': 3600}, request=req)
        req = httpx.Request('POST', url)
        return httpx.Response(
            422,
            json={
                'name': 'UNPROCESSABLE_ENTITY',
                'message': 'Compliance check failed for transaction',
                'debug_id': 'dbg_paypal_998877'
            },
            request=req
        )

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)

    with pytest.raises(HTTPException) as exc_info:
        await paypal.create_order('purchase-err', {'name': 'Test', 'price': '24.00'})
    assert exc_info.value.status_code == 502
    detail = exc_info.value.detail
    assert 'UNPROCESSABLE_ENTITY' in detail
    assert 'Compliance check failed' in detail
    assert 'dbg_paypal_998877' in detail


def test_capture_verified_rejects_uncertain_incomplete_or_mismatched():
    """Verify capture_verified rejects missing captures, mismatched amount, wrong reference, or incomplete status."""
    base_item = {'price': '24.00'}

    # 1. Status not COMPLETED
    res = {'status': 'PENDING', 'purchase_units': [{'reference_id': 'pid-1', 'payments': {'captures': [{'id': 'c1', 'status': 'COMPLETED', 'amount': {'currency_code': 'USD', 'value': '24.00'}}]}}]}
    assert paypal.capture_verified(res, 'pid-1', base_item) is None

    # 2. Reference ID mismatch
    res = {'status': 'COMPLETED', 'purchase_units': [{'reference_id': 'pid-WRONG', 'payments': {'captures': [{'id': 'c1', 'status': 'COMPLETED', 'amount': {'currency_code': 'USD', 'value': '24.00'}}]}}]}
    assert paypal.capture_verified(res, 'pid-1', base_item) is None

    # 3. Capture record status not COMPLETED
    res = {'status': 'COMPLETED', 'purchase_units': [{'reference_id': 'pid-1', 'payments': {'captures': [{'id': 'c1', 'status': 'PENDING', 'amount': {'currency_code': 'USD', 'value': '24.00'}}]}}]}
    assert paypal.capture_verified(res, 'pid-1', base_item) is None

    # 4. Amount mismatch (e.g. buyer paid $10.00 instead of $24.00)
    res = {'status': 'COMPLETED', 'purchase_units': [{'reference_id': 'pid-1', 'payments': {'captures': [{'id': 'c1', 'status': 'COMPLETED', 'amount': {'currency_code': 'USD', 'value': '10.00'}}]}}]}
    assert paypal.capture_verified(res, 'pid-1', base_item) is None

    # 5. Currency mismatch
    res = {'status': 'COMPLETED', 'purchase_units': [{'reference_id': 'pid-1', 'payments': {'captures': [{'id': 'c1', 'status': 'COMPLETED', 'amount': {'currency_code': 'EUR', 'value': '24.00'}}]}}]}
    assert paypal.capture_verified(res, 'pid-1', base_item) is None

    # 6. Valid exact match returns capture ID
    res = {'status': 'COMPLETED', 'purchase_units': [{'reference_id': 'pid-1', 'payments': {'captures': [{'id': 'c1', 'status': 'COMPLETED', 'amount': {'currency_code': 'USD', 'value': '24.00'}}]}}]}
    assert paypal.capture_verified(res, 'pid-1', base_item) == 'c1'

