# LicenseFlow Guard — PayPal Sandbox Payment Reference

**Project:** LicenseFlow Guard (PayPal AI Hackathon 2026)  
**Document date:** 4 November 2026  
**Environment:** PayPal **Sandbox only**  
**Purpose:** Reusable test-payment details, verified sample transaction evidence, and the remaining validation steps.

> **Safety:** Use these values only on a PayPal Sandbox checkout page. Never enter real card details, real personal information, bank credentials, or live PayPal passwords. The billing information below is fictional; the card number is PayPal-published test data.

## 1. Verify before entering payment information

Confirm all of the following in LicenseFlow Guard before opening or submitting checkout:

- The page indicates **PAYPAL SANDBOX**.
- The selected dataset is **Customer Support Intent Mini** (`support-intent`).
- The checkout amount is **USD 24.00**.
- The selected rights permit **commercial use** and **model training**; **redistribution** is not permitted.
- A **fresh server-bound approval quote** has been generated and is still valid (the UI displays a 10-minute lifetime).
- The quote corresponds to the same dataset, price, currency, and rights currently displayed.

Do not reuse an expired or already consumed quote. **A successful dataset-matching result does not authorize payment.**

## 2. PayPal Sandbox card details

| Form field | Value |
|---|---|
| Card type | Visa (PayPal-published sandbox test number) |
| Card number | `4012 0000 3333 0026` |
| Expiration (MM/YY) | `12/29` |
| Security code / CVV | `123` |

**Source and limitations:** PayPal's [official sandbox card-testing documentation](https://developer.paypal.com/sandbox-testing/card-testing) lists this Visa card number and permits a future expiry date with a three-digit Visa CVV. The specific expiration and CVV above are *illustrative test values* and are not PayPal-issued personal credentials. Acceptance may depend on the integration and test configuration.

## 3. Example UK test billing information

The sample checkout screenshot selected **United Kingdom** as the billing country. These values reproduce that fictional test scenario:

| Form field | Test-only value |
|---|---|
| Billing country | United Kingdom |
| First name | `Test` |
| Last name | `Buyer` |
| Address line 1 | `10 Example Street` |
| Address line 2 | Leave blank |
| Town / City | `London` |
| County | `London` (optional, if requested) |
| Postcode | `SW1A 1AA` |
| Mobile (+44) | `7700900123` |
| Email | `testbuyer@example.com` (example address; no inbox) |
| Deliver to billing address | Checked, if the form requires it |

These are **synthetic examples**, not a verified identity, issued account, or deliverable address. If the guest-card flow rejects them, do not substitute real financial information. Use a **Personal Sandbox buyer account** from the [PayPal Sandbox Accounts dashboard](https://developer.paypal.com/dashboard/accounts) instead. PayPal explains that Personal sandbox accounts act as buyers and Business sandbox accounts act as sellers: [Sandbox accounts documentation](https://developer.paypal.com/sandbox-testing/accounts).

## 4. Checkout procedure

1. In the application, choose **Customer Support Intent Mini** and confirm it passes the deterministic rights and budget checks.
2. Review its illustrative rights manifest and generate a fresh server-bound approval quote.
3. Open **Pay with PayPal** or **Debit or Credit Card** in the **sandbox** checkout.
4. Enter the test card and fictional billing details from Sections 2–3, or sign in with your Personal Sandbox buyer account.
5. Verify **USD 24.00** and submit the payment **once**.
6. After checkout, verify the application shows a genuine capture reference and unlocked **Download Verified Dataset** / **Download Provenance Receipt** actions.
7. Check the payment in the Business merchant's [PayPal Sandbox activity](https://www.sandbox.paypal.com/). The UI message alone is not independent proof of settlement status.

Do not initiate additional sandbox payments simply to repeat evidence already collected. Prefer read-only status checks when reviewing the existing transaction.

## 5. Latest completed sandbox test — observed evidence

The following values come from the project's second uploaded JSON receipt and downloaded CSV, accompanying the application's capture-confirmed screenshot.

| Field | Observed value |
|---|---|
| Sandbox | `true` |
| Dataset | `Customer Support Intent Mini` (`support-intent`) |
| Amount | **USD 24.00** |
| PayPal order ID | `3FX883057R390593U` |
| PayPal capture ID | `3E583077NN119930W` |
| Project purchase ID | `64a73dd7-a3f8-4083-8135-56b66180a4d6` |
| Server approval ID | `9f6a6119-0f28-46fc-b26d-a821da35b348` |
| CSV data records | **48** (excluding header) |
| Downloaded CSV size | **2,547 bytes** |
| Demonstration license ID | `LF-DEMO-C1` |
| Commercial use | Permitted |
| Model training | Permitted |
| Redistribution | Not permitted |

**Recorded SHA-256 (full digest):**

```text
1f197bc7bffa8378c21eb4537be87021dfb9db2bedbf910cbe709f8f0f1487ff
```

**Verified integrity:** The uploaded file `support-intent (1).csv` hashes to **exactly** that digest, matching the uploaded `licenseflow-receipt (1).json`.

### What this evidence means

- The application displayed a completed PayPal Sandbox capture and provided the dataset and receipt.
- The downloaded CSV and the receipt are **internally consistent**.
- The receipt identifies the server approval involved in the upgraded purchase flow.
- This **does not independently establish** the capture status held by PayPal, cryptographically authenticate the receipt, or certify legal rights to a real-world dataset. The dataset and its license are expressly synthetic/illustrative.

## 6. Next three actions

| Owner | Deliverable | Success criterion |
|---|---|---|
| Project owner | Confirm capture `3E583077NN119930W` for USD 24.00 in the merchant's PayPal Sandbox account or a read-only capture-details check | Payment recorded as completed; retain a redacted screenshot or log |
| Antigravity CLI | Independently rerun the **35-test** suite and review approval binding, replay, concurrency, downloads, and capture recovery | Evidence of actual passed/failed counts and no unresolved P0 issues |
| Project owner + assistant | Freeze the core, finalize the open-source repository, reproducible README, and public YouTube demonstration under three minutes | Devpost submission completed before **13 November 2026, 1:30 AM IST** |

## 7. Official documentation

- [PayPal — Sandbox card testing](https://developer.paypal.com/sandbox-testing/card-testing)
- [PayPal — Sandbox accounts](https://developer.paypal.com/sandbox-testing/accounts)
- [PayPal — Sandbox testing overview](https://developer.paypal.com/sandbox-testing/overview/)
- [PayPal — Payments v2 API / captured payment details](https://developer.paypal.com/docs/api/payments/v2/)
- [Devpost — PayPal AI Hackathon official rules](https://paypalaihackathon.devpost.com/rules)

---

*LicenseFlow Guard · Sandbox-only development reference · 4 November 2026*
