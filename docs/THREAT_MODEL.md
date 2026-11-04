# Threat Model — LicenseFlow AI MVP

| Asset / boundary | Threat | Control present | Residual risk / next control |
|---|---|---|---|
| PayPal seller secret | Credential theft | Server-side environment variable; sandbox-only endpoint; never transmitted to LLM/browser | Centralized secret management and key rotation before production |
| Buyer payment authorization | AI initiates spending | AI has no payment tools; buyer manually initiates checkout in PayPal SDK | Authentication and buyer account binding required for hosted multiuser version |
| Price and SKU | Client tampers with amount | Server reads price from static trusted catalog, not client | Catalog versioning and database transactions |
| Dataset license | AI hallucinates rights | Deterministic hard filters; AI ranks only eligible IDs; server revalidates | Genuine seller license verification and legal review |
| Dataset after checkout | Unpaid access | Authenticated bearer receipt token derived via HMAC only after verified capture | Real user auth, short-lived tokens, revoke capability |
| Capture result | Forged success | Server calls PayPal directly; checks reference ID, currency, amount, completion | Signed webhooks, order GET reconciliation, idempotency collision handling |
| Untrusted model text | Prompt injection / HTML | No payment tools; untrusted fields as data; plain-text DOM rendering | Adversarial prompt corpus and regressions |
| App availability | Model/PayPal outage | Explicit 502/503 errors; no fake success | Retries/reconciliation/alerts/SLOs |
| Cost / abuse | Unauthenticated repeated AI calls | Disabled without server API key; local-only default | **Critical**: auth, rate limits, budgets before public deployment |
| File provenance | Malicious or wrongly owned dataset | Only self-created synthetic CSV and SHA-256 hash | Legitimate vendor attestations and signed licenses |

**Standards mapping (design guidance, not certification):** OWASP LLM01 prompt injection; OWASP API1 broken object-level authorization (production gap); OWASP API4 unrestricted resource consumption (production gap); NIST AI RMF Govern/Map/Measure/Manage; NIST SSDF for test and release discipline. No penetration test has been performed. No authorization is granted to test real PayPal infrastructure outside published sandbox interfaces.
