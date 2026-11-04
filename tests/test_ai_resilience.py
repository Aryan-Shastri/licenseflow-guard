"""Unit tests for Gemini model selection, error classification, bounded retries,
caching, and deterministic output filtering.
All tests are strictly mocked locally; no live Gemini API calls are made.
"""
import pytest
from google.genai import errors
import app.ai as ai
from app.ai import MatchOutput, Choice, classify_error, _cache_key
from app.catalog import get_entry

ELIGIBLE_SUPPORT = [get_entry('support-intent')]
GOAL = "I need commercial customer support training data"


@pytest.fixture(autouse=True)
def clean_cache():
    ai.clear_cache()


def test_classify_error_404_invalid_model():
    err = errors.ClientError(404, {'error': {'code': 404, 'message': 'models/gemini-invalid is not found'}})
    cat, is_transient = classify_error(err)
    assert cat == 'INVALID_MODEL'
    assert is_transient is False


def test_classify_error_429_daily_quota():
    err = errors.ClientError(429, {'error': {'code': 429, 'message': 'Resource has been exhausted (e.g. check quota). Quota metric: Per-day request limit exceeded.'}})
    cat, is_transient = classify_error(err)
    assert cat == 'DAILY_QUOTA_EXHAUSTED'
    assert is_transient is False


def test_classify_error_429_transient_rate_limit():
    err = errors.ClientError(429, {'error': {'code': 429, 'message': 'Rate limit exceeded: 15 requests per minute.'}})
    cat, is_transient = classify_error(err)
    assert cat == 'TRANSIENT_RATE_LIMIT'
    assert is_transient is True


def test_classify_error_503_overload():
    err = errors.ServerError(503, {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Please try again later.'}})
    cat, is_transient = classify_error(err)
    assert cat == 'TRANSIENT_SERVER_ERROR'
    assert is_transient is True


def test_404_fails_fast_without_retry(monkeypatch):
    """404 must fail immediately on attempt 1 without retries or switching to fallback."""
    call_log = []

    class MockModels:
        def generate_content(self, model, contents, config):
            call_log.append(model)
            raise errors.ClientError(404, {'error': {'code': 404, 'message': 'Model not found'}})

    class MockClient:
        def __init__(self, api_key):
            self.models = MockModels()

    monkeypatch.setenv('GEMINI_API_KEY', 'mock-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.5-flash')
    monkeypatch.setattr('google.genai.Client', MockClient)

    with pytest.raises(errors.ClientError) as exc_info:
        ai._rank(GOAL, ELIGIBLE_SUPPORT)

    assert exc_info.value.code == 404
    # Verified: exactly 1 call was made to primary model; no retry and no fallback!
    assert call_log == ['gemini-3.5-flash-lite']


def test_429_daily_quota_fails_fast_without_retry(monkeypatch):
    """Daily quota exhaustion (429) must fail immediately without retry or model switching."""
    call_log = []

    class MockModels:
        def generate_content(self, model, contents, config):
            call_log.append(model)
            raise errors.ClientError(429, {'error': {'code': 429, 'message': 'Quota exceeded: 20 queries per day.'}})

    class MockClient:
        def __init__(self, api_key):
            self.models = MockModels()

    monkeypatch.setenv('GEMINI_API_KEY', 'mock-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.5-flash')
    monkeypatch.setattr('google.genai.Client', MockClient)

    with pytest.raises(errors.ClientError) as exc_info:
        ai._rank(GOAL, ELIGIBLE_SUPPORT)

    assert exc_info.value.code == 429
    # Verified: exactly 1 call was made to primary model; zero retries to prevent quota burn
    assert call_log == ['gemini-3.5-flash-lite']


def test_429_transient_rate_limit_bounded_retry(monkeypatch):
    """Transient per-minute rate limit allows at most 1 bounded retry on the same model."""
    call_log = []

    class MockResponse:
        text = '{"rationale": "Transient recovery successful", "choices": [{"dataset_id": "support-intent", "explanation": "Fits support goal", "limitation": "Small size"}]}'

    class MockModels:
        def generate_content(self, model, contents, config):
            call_log.append(model)
            if len(call_log) == 1:
                raise errors.ClientError(429, {'error': {'code': 429, 'message': 'Rate limit exceeded: 15 per minute'}})
            return MockResponse()

    class MockClient:
        def __init__(self, api_key):
            self.models = MockModels()

    monkeypatch.setenv('GEMINI_API_KEY', 'mock-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    monkeypatch.setattr('time.sleep', lambda s: None)  # fast test
    monkeypatch.setattr('google.genai.Client', MockClient)

    result = ai._rank(GOAL, ELIGIBLE_SUPPORT)
    assert result.rationale == "Transient recovery successful"
    # Exactly 2 calls to primary model: initial attempt + 1 bounded retry
    assert call_log == ['gemini-3.5-flash-lite', 'gemini-3.5-flash-lite']


def test_503_model_overload_retry_and_fallback(monkeypatch):
    """Primary 503 overload retries once, then gracefully switches to fallback model."""
    call_log = []

    class MockResponse:
        text = '{"rationale": "Fallback model successful", "choices": [{"dataset_id": "support-intent", "explanation": "Fits support goal", "limitation": "Small size"}]}'

    class MockModels:
        def generate_content(self, model, contents, config):
            call_log.append(model)
            if model == 'gemini-3.5-flash-lite':
                raise errors.ServerError(503, {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}})
            return MockResponse()

    class MockClient:
        def __init__(self, api_key):
            self.models = MockModels()

    monkeypatch.setenv('GEMINI_API_KEY', 'mock-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.5-flash')
    monkeypatch.setattr('time.sleep', lambda s: None)
    monkeypatch.setattr('google.genai.Client', MockClient)

    result = ai._rank(GOAL, ELIGIBLE_SUPPORT)
    assert result.rationale == "Fallback model successful"
    # Primary attempted twice (initial + 1 bounded retry), then fallback succeeded once
    assert call_log == ['gemini-3.5-flash-lite', 'gemini-3.5-flash-lite', 'gemini-3.5-flash']


@pytest.mark.anyio
async def test_recommendation_caching(monkeypatch):
    """Identical requests must hit the in-memory cache and skip the network/model call."""
    call_count = 0

    def fake_rank(goal, eligible):
        nonlocal call_count
        call_count += 1
        return MatchOutput(
            rationale="Calculated advice",
            choices=[Choice(dataset_id="support-intent", explanation="Good fit", limitation="Sample only")]
        )

    monkeypatch.setattr(ai, '_rank', fake_rank)

    # First call: cache miss
    res1 = await ai.match(GOAL, ELIGIBLE_SUPPORT)
    assert call_count == 1
    assert res1['model_used'] is True

    # Second call with identical goal and dataset: cache hit!
    res2 = await ai.match(GOAL, ELIGIBLE_SUPPORT)
    assert call_count == 1  # Network/rank call NOT invoked!
    assert res2['choices'][0]['dataset_id'] == 'support-intent'

    # Third call with different goal: cache miss
    res3 = await ai.match("Different goal query", ELIGIBLE_SUPPORT)
    assert call_count == 2


@pytest.mark.anyio
async def test_untrusted_output_filtering_preserved(monkeypatch):
    """Model output containing ineligible or hallucinated IDs must be filtered out."""
    def fake_rank(goal, eligible):
        return MatchOutput(
            rationale="Advisory with extra IDs",
            choices=[
                Choice(dataset_id="support-intent", explanation="Eligible", limitation="None"),
                Choice(dataset_id="civic-dialogue", explanation="Non-commercial", limitation="Restricted"),
                Choice(dataset_id="hallucinated-id-999", explanation="Fake", limitation="Fake")
            ]
        )

    monkeypatch.setattr(ai, '_rank', fake_rank)
    res = await ai.match(GOAL, ELIGIBLE_SUPPORT)
    chosen_ids = [c['dataset_id'] for c in res['choices']]
    assert 'support-intent' in chosen_ids
    assert 'civic-dialogue' not in chosen_ids
    assert 'hallucinated-id-999' not in chosen_ids
