# Devpost Submission — LicenseFlow Guard v1.0

## Project Information
- **Project Title:** LicenseFlow Guard
- **Tagline:** Rights-aware AI dataset discovery, deterministic policy enforcement, PayPal Sandbox checkout, cryptographic provenance receipts, and AG Grid procurement intelligence.
- **Repository URL:** https://github.com/Aryan-Shastri/licenseflow-guard
- **Tracks / Categories:**
  - Main Track: PayPal AI Hackathon 2026
  - Sponsor Track: APIMatic PayPal Integration
  - Sponsor Track: AG Grid / AG Studio Enterprise Analytics

---

## Pitch & Overview

### Inspiration
AI engineering teams and enterprise ML researchers face an urgent legal and operational governance dilemma: procuring high-quality datasets while ensuring explicit, machine-readable licensing rights (commercial use, model training, and no unauthorized raw redistribution) *before* committing company funds.

Existing payment bots and e-commerce carts treat datasets like physical goods: they execute payments blindly without validating licensing compatibility, leaving organizations vulnerable to copyright litigation, intellectual property contamination, and budget overruns.

We built **LicenseFlow Guard** to bridge this gap: an AI-assisted dataset commerce platform where machine-readable licensing rules serve as a **hard deterministic gate** before payment, tying an authenticated PayPal capture to an immutable, cryptographic byte-level provenance receipt, all monitored via an enterprise **AG Grid** procurement audit dashboard.

---

## What It Does

1. **Deterministic Licensing & Budget Gate**: The user specifies their engineering mission, maximum budget, and required rights (Commercial Use, Model Training, Redistribution). The deterministic policy engine immediately checks declared license manifests (`LF-DEMO-C1`, `LF-DEMO-NC`, etc.) and blocks incompatible products with explicit, explainable rationales.
2. **Resilient AI Advisory Matching**: Google Gemini (`gemini-3.5-flash-lite`, 500 RPD) provides structured advisory rankings and practical limitations exclusively for policy-eligible datasets. Model outputs are treated as untrusted and cannot override policy or authorize payments.
3. **Server-Bound Approval Quotes**: Prevents client-side price or parameter tampering through a single-use, 10-minute server-persisted approval quote (`/api/quotes`) cryptographically bound to the dataset ID, snapshot price, currency `USD`, and rights terms.
4. **Hardened PayPal Sandbox Orders v2 (APIMatic Integration)**: Using specifications from the official **APIMatic PayPal Context Plugin**, the server manages in-memory OAuth2 token caching with proactive refresh, injects `Prefer: return=representation` headers, and enforces an atomic state machine (`ORDER_CREATED -> CAPTURING -> COMPLETED`). If a network drop occurs during capture, read-only reconciliation queries verify order completion before failing closed.
5. **Cryptographic Provenance Receipts**: When PayPal confirms payment, access to the dataset is granted via an HMAC-signed bearer token. The buyer receives a downloadable provenance receipt containing the PayPal capture ID, timestamp, and the dataset's SHA-256 digest matching the delivered CSV byte-for-byte.
6. **AG Grid Procurement Security Intelligence Dashboard**: An interactive audit dashboard powered by **AG Grid Community v32** and **AG Charts Community v10**, displaying real-time spend, completed capture references, deterministic policy refusals, and security defenses with multi-column filtering, search, keyboard accessibility, and CSV audit export.
7. **Air-Gapped Telemetry Advisor**: An advisory intelligence assistant answering natural language audit queries while strictly prohibited from executing financial transactions.

---

## How We Built It

- **Backend**: Python 3.15, FastAPI, SQLite, HTTPX, Pydantic, and hashlib/hmac for constant-time cryptographic verification.
- **AI Integration**: Google GenAI SDK with automated fallback chain (`gemini-3.5-flash-lite` → `gemini-3.7-flash` → `gemini-3.5-flash`), in-memory recommendation caching, quota exhaustion protection, and transient overload retries.
- **Payment Rail**: PayPal Sandbox Orders v2 REST API and PayPal JavaScript SDK v5. Hardened using APIMatic specifications.
- **Analytics & Governance**: AG Grid Community (`v32.2.0`) and AG Charts Community (`v10.2.0`) with custom dark & lime cyber-security theming. Local offline vendor bundling in `static/vendor/` for air-gapped evaluation.
- **Security & Testing**: 50 automated tests across policy enforcement, AI resilience, PayPal timeout reconciliation, audit API security, and 10 adversarial regression fixtures.

---

## Challenges We Ran Into

1. **Gemini Upstream Quota & Overload**: During development, `gemini-3.8-flash` experienced upstream 503 overload spikes. We engineered an intelligent resilience layer prioritizing `gemini-3.5-flash-lite` (500 RPD free tier) with deterministic in-memory caching and bounded retries.
2. **Ambiguous Network Drops During Capture**: An HTTP network disconnect during order capture leaves payments in an uncertain state. We implemented APIMatic's recommended read-only reconciliation pattern (`GET /v2/checkout/orders/{id}`) to verify PayPal capture status before failing closed.
3. **Sponsor Integration Transparency**: Evaluating the enterprise `ag-studio` package revealed commercial licensing terms and a 6.7MB bundle. Rather than falsely claiming full closed-source Studio deployment or modifying open-source terms, we integrated genuine AG Grid Community v32 & AG Charts v10 for our primary application, created an explicit feasibility harness at `/ag_studio_feasibility.html`, and accurately reported our architecture.

---

## Accomplishments We're Proud Of

- **100% Automated Test Pass Rate**: All 50 unit, integration, and security tests pass cleanly in under 6 seconds.
- **Zero Payment Replays & Parameter Tampering**: Cryptographically bound server quotes prevent replay attacks (409 Conflict) and cross-dataset price tampering (422 Unprocessable Entity).
- **Byte-Level Traceability**: Completed purchases produce an auditable receipt linking the PayPal Sandbox capture ID to the exact SHA-256 content hash of the delivered dataset.
- **Dual Sponsor Alignment**: Genuine, documented technical contributions from both APIMatic and AG Grid.

---

## What We Learned

- How to design AI agents as strictly advisory assistants that provide business value without granting them dangerous direct access to payment or financial authorization endpoints.
- Best practices from APIMatic for enterprise payment resiliency, including double-checked locking for OAuth2 token caches and timeout reconciliation.
- How AG Grid's virtualization and column filter architecture enables high-performance compliance auditing without complex frontend frameworks.

---

## What's Next for LicenseFlow Guard

- Enterprise Single Sign-On (SAML/Okta) for multi-user organizational procurement approval workflows.
- Webhook ingestion with cryptographic signature validation (`PAYPAL-AUTH-ALGO`).
- Multi-currency conversion and automated vendor payout splits via PayPal Payouts.
