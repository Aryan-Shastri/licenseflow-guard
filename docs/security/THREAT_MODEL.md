# Threat Model & Security Controls — LicenseFlow Guard

## Security Boundary Matrix

| Asset / Boundary | Threat | Control Present in LicenseFlow Guard | Residual Risk / Future Production Control |
|---|---|---|---|
| **PayPal Seller Secret** | Credential theft | Stored only in server environment variable; restricted to `api-m.sandbox.paypal.com`; never logged, printed, or sent to client/LLM. | Centralized HSM / Vault secret management and automated rotation before production deployment. |
| **Buyer Approval / Consent** | Browser-only tampering / bypass | **Server-persisted single-use quote** (`POST /api/quotes`) cryptographically binds dataset ID, price ($24.00), currency (USD), rights snapshot, intent, and expiry (10 min). Order creation requires valid `quote_id` and `approval_token`. | Production OAuth2/OIDC user authentication with session binding and multi-factor approval. |
| **Approval Replay & Forgery** | Replay of consumed approval token | Token hashed with SHA-256; atomic compare-and-swap consumes token upon order creation (`UPDATE approvals SET status='CONSUMED' WHERE status='APPROVED'`). Replays return 409 Conflict. | Distributed token cache with cluster-wide eviction. |
| **Price / Catalog Tampering** | Client alters amount or SKU | Server reads price from immutable server-bound quote snapshot; PayPal order creation and capture verification enforce exact dollar amount. | Vendor ledger with signed cryptographic manifests. |
| **Concurrent Double-Capture** | Parallel capture requests | State machine enforces atomic `ORDER_CREATED -> CAPTURING -> COMPLETED` via DB compare-and-swap; duplicate requests return cached completion idempotently. Deterministic `PayPal-Request-Id` header sent. | Distributed lock (e.g., Redis Redlock) for multi-node deployments. |
| **Payment Verification** | Forged or mismatched capture | Direct server-to-server call to PayPal Orders v2; strict validation of order reference ID, currency `USD`, capture status `COMPLETED`, and exact price match. | PayPal signed webhook ingestion (`PAYMENT.CAPTURE.COMPLETED`) with cert chain verification. |
| **Data Download & Receipt** | Unpaid / premature access | Access token derived via HMAC-SHA256 (`APP_SIGNING_KEY`); endpoints strictly require `status == 'COMPLETED'`. No access in `CREATING`, `ORDER_CREATED`, `CAPTURING`, or `FAILED` states. | Short-lived signed download URLs (e.g., S3 presigned URLs with 60s TTL). |
| **AI Prompt Injection** | Adversarial text in catalog/goal | AI output is treated as untrusted data; only catalog IDs passing deterministic `policy.py` checks are accepted. AI has no payment tools, no DB access, and no capture capability. | External input guardrails and sandboxed inference runners. |
| **AI Upstream Availability** | High-demand 503 / 429 spikes | Resilient fallback chain (primary `gemini-3.8-flash` -> `gemini-3.7-flash` -> `gemini-3.5-flash`) with exponential retry and safe sanitized error reporting. Deterministic filters always available. | Circuit breaker and local embedding cache. |
| **Catalog Snapshot Integrity** | Catalog altered after purchase | Purchase records snapshot `snapshot_price`, `snapshot_currency`, `snapshot_license_id`, `snapshot_sha256` at creation time. Receipts remain permanently immutable. | Immutable append-only audit log. |

---

## Adversarial Test Suite Coverage

A dedicated test suite ([`tests/test_security_adversarial.py`](../../tests/test_security_adversarial.py)) verifies the following 10 threat scenarios:

1. **`test_adv_01_prompt_injection_cannot_override_policy`**: Jailbreak/injection attempt in user goal fails against deterministic budget check.
2. **`test_adv_02_unapproved_purchase_attempt_blocked`**: Direct purchase attempt without server quote returns 403 Forbidden.
3. **`test_adv_03_approval_replay_rejected`**: Replay of consumed approval token returns 409 Conflict.
4. **`test_adv_04_cross_dataset_quote_binding_tampering`**: Token generated for $24 item used on $34 item returns 422 Unprocessable Entity.
5. **`test_adv_05_expired_quote_rejected`**: Quote older than 10 minutes returns 410 Gone.
6. **`test_adv_06_unauthorized_premature_download_blocked`**: Download attempts before completion or with forged tokens return 403 Forbidden.
7. **`test_adv_07_tampered_paypal_capture_amount_rejected`**: Capture returning mismatched amount ($1.00 vs $24.00) sets order to FAILED and denies data access.
8. **`test_adv_08_tampered_paypal_reference_id_rejected`**: Capture returning foreign reference ID fails verification.
9. **`test_adv_09_catalog_tampering_isolation`**: Mutating catalog prices post-purchase does not alter historic receipt values.
10. **`test_adv_10_concurrent_capture_race_protection`**: Simultaneous capture calls execute exactly once and return idempotent completed response.

---

## Standards Alignment (Educational / Prototype Scope)

- **OWASP Top 10 for LLM Applications:**
  - *LLM01 (Prompt Injection):* Addressed via architectural separation: LLM does not execute actions or set policies.
  - *LLM06 (Sensitive Information Disclosure):* Sanitized logging ensures API keys and PII are never output.
- **OWASP API Security Top 10:**
  - *API1 (Broken Object Level Authorization):* HMAC-authenticated token verification required on all resource accesses.
  - *API8 (Security Misconfiguration):* Sandboxed payment rails, strictly disabled in production.
- **Scope Notice:** These controls represent local application defenses for hackathon demonstration. No penetration testing of live third-party infrastructure was conducted. Live payments are restricted to PayPal Sandbox.
