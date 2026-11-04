# Public YouTube Demo Script — LicenseFlow Guard (~3 Minutes)

**Goal:** Deliver a crisp, compliant, continuous demonstration of evidence-backed dataset recommendation, deterministic refusal of unsuitable data, server-bound approval, PayPal Sandbox capture, and auditable receipt verification.

---

### Timing & Script Progression

#### 0:00 – 0:25: The Problem & Solution Overview
- **Visual:** Open LicenseFlow Guard UI (`http://127.0.0.1:8000`). Point to the top bar: "PayPal Sandbox", "Hackathon Edition · 2026".
- **Speaker:** "AI engineering teams face a serious governance challenge: finding datasets with explicit, legally compatible rights before spending company funds. Procurement spreadsheets and generic payment bots lack verifiable rights enforcement. LicenseFlow Guard solves this by making machine-readable licensing rules an authoritative gate *before* payment, tying PayPal capture to a cryptographic byte-level receipt."

#### 0:25 – 0:55: Deterministic Refusal Demo (Explainable Governance Gate)
- **Visual:** Set Intent in Panel 1:
  - Goal: `I need a labeled dataset to train a commercial customer-support classifier. I cannot redistribute the raw dataset.`
  - Budget: `$35.00 USD`
  - Required Rights: Commercial Use [✓], Model Training [✓], Redistribution [ ]
- **Action:** Click **"Apply Rights Filter Only"**.
- **Visual:** In Panel 2 (Explore Collection), observe:
  - `support-intent` ($24.00) is tagged `RIGHTS-MATCHED`.
  - `civic-dialogue` is tagged `RESTRICTED: Not licensed for commercial use (LF-DEMO-R1)`.
  - `retail-demand` is tagged `RESTRICTED: Above the selected budget ($44.00 > $35.00)`.
- **Action:** Click on `civic-dialogue`. Show Panel 3: "PURCHASE BLOCKED: Not licensed for commercial use". Checkbox is disabled.
- **Speaker:** "Notice that our deterministic policy engine refuses `civic-dialogue` immediately. No prompt injection or AI reasoning can override this hard policy boundary."

#### 0:55 – 1:25: AI Matching with Gemini (Untrusted Advisory Ranking)
- **Action:** Click **"Match with AI"**.
- **Visual:** The AI advisory box populates with structured ranking and rationale. Only policy-approved datasets (`support-intent`) appear in recommendations, complete with practical limitations (e.g., small synthetic sample size).
- **Speaker:** "Gemini acts strictly as an advisory assistant. It provides recommendations and limitations, but the backend treats AI output as untrusted data: only catalog IDs that passed our deterministic gate are accepted."

#### 1:25 – 2:10: Server-Bound Approval & Real PayPal Sandbox Checkout
- **Action:** Select `support-intent` ($24.00). Review the Rights Manifest (LF-DEMO-C1) and SHA-256 content hash.
- **Action:** Check **"Review rights manifest and generate a server-bound approval quote"**.
- **Visual:** A green quote box appears:
  `✓ SERVER-BOUND APPROVAL QUOTE REGISTERED: Bound to Customer Support Intent Mini · $24.00 USD (Single-Use, 10 min validity)`.
- **Speaker:** "Notice our server-bound approval gate: checking this box creates a single-use, cryptographic server quote binding the exact price, currency, dataset ID, and rights snapshot. Tampering with any parameter or replaying an old quote will fail closed."
- **Action:** Click the PayPal button. Log in with personal Sandbox buyer credentials and approve payment. Keep the checkout window in a continuous take.

#### 2:10 – 2:40: Server Capture Verification & Receipt Audit
- **Visual:** Modal closes. Status transitions:
  `Verifying PayPal capture and reconciling with order binding...` -> `PayPal sandbox capture verified. Dataset access granted.`
- **Visual:** Panel scrolls smoothly to **"Capture Confirmed"**.
  - PayPal Capture ID displayed (e.g., `85N88457G5963280B`).
  - Dataset SHA-256 displayed (`1f197bc...`).
- **Action:** Click **"Download Provenance Receipt"** (JSON) and **"Download Verified Dataset"** (CSV).
- **Speaker:** "The backend verified the PayPal capture status, currency USD, exact amount $24.00, and purchase reference before minting a signed HMAC bearer token. The receipt contains the immutable snapshot taken at quote time."

#### 2:40 – 3:00: Honest Security Disclosure & Conclusion
- **Speaker:** "All catalog entries, licenses, and CSVs in this prototype are synthetic demonstrations, not formal legal guarantees. The payment rail is strictly PayPal Sandbox. LicenseFlow Guard brings policy enforcement and cryptographic traceability to AI dataset commerce. Thank you."

---

### Demo Pre-Flight Checklist
1. FastAPI backend running on `http://127.0.0.1:8000`.
2. PayPal sandbox business and personal credentials confirmed active.
3. Gemini API key configured with resilient fallback chain.
4. Screen recorder set to 1080p, audio clear, no visible passwords or API keys.
5. Max video duration: **under 3 minutes** (Devpost disqualifies videos > 3:00).
