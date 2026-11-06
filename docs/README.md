# LicenseFlow Guard — Documentation Index

This directory contains the technical documentation, security specifications, sponsor integration references, and release assets for **LicenseFlow Guard** (PayPal AI Hackathon 2026).

---

## Directory Organization

```
docs/
├── README.md                              # This documentation index
├── architecture/
│   └── PROJECT_BRIEF.md                   # Product brief, user journeys, sequence flows & MVP scope
├── security/
│   └── THREAT_MODEL.md                    # Threat matrix, adversarial defenses & security controls
├── sponsors/
│   └── PAYPAL_SANDBOX_REFERENCE.md        # PayPal Sandbox test credentials, card data & verification
├── development/
│   └── ENGINEERING_HANDOFF.md             # Baseline handoff, environment setup & implementation work packages
└── release/
    ├── DEVPOST_SUBMISSION.md              # Official Devpost submission write-up, pitch & sponsor disclosures
    └── DEMO_SCRIPT.md                     # Timed 3-minute video presentation script for hackathon judges
```

---

## Documentation Categories

| Category | Primary Document | Purpose |
| :--- | :--- | :--- |
| **Release & Submission** | [`release/DEVPOST_SUBMISSION.md`](release/DEVPOST_SUBMISSION.md) | Official hackathon submission overview, project pitch, sponsor integration evidence, challenges, and accomplishments. |
| **Demo Video** | [`release/DEMO_SCRIPT.md`](release/DEMO_SCRIPT.md) | Step-by-step timed (~3 minute) judge walkthrough script covering policy refusal, AI matching, PayPal Sandbox checkout, receipts, and AG Grid analytics. |
| **Architecture** | [`architecture/PROJECT_BRIEF.md`](architecture/PROJECT_BRIEF.md) | Core product brief, buyer persona, deterministic policy sequence, and prototype scope boundaries. |
| **Security & Auditing** | [`security/THREAT_MODEL.md`](security/THREAT_MODEL.md) | Comprehensive threat model matrix, OWASP Top 10 for LLMs alignment, and documentation of the 10 adversarial regression test fixtures. |
| **Sponsor Tracks** | [`sponsors/PAYPAL_SANDBOX_REFERENCE.md`](sponsors/PAYPAL_SANDBOX_REFERENCE.md) | PayPal Developer Sandbox configuration, test payment card values, capture verification procedures, and APIMatic resilience patterns. |
| **Development** | [`development/ENGINEERING_HANDOFF.md`](development/ENGINEERING_HANDOFF.md) | Engineering handoff specification, local workspace commands, and implementation work packages. |

---

## Quick Navigation

- Return to project root: [README.md](../README.md)
- View license: [LICENSE](../LICENSE)
- View local environment template: [.env.example](../.env.example)
