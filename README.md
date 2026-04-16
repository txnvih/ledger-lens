# LedgerLens — Payments Reconciliation Engine

> Find out why the books don't balance. Instantly.

---

## What It Does

- **Assumptions**
  - Every transaction has a shared `txn_id` across platform and bank
  - Amounts compared with ±0.01 tolerance (rounding noise)
  - A negative bank amount = reversal / refund
  - Same-month settlement window; FX conversion is out of scope
  - `txn_id` collision on the platform side = genuine duplicate booking

- **Six Gap Types Detected**

  | Class | Severity | Meaning |
  |---|---|---|
  | `missing_in_bank` | High | Platform recorded it — bank never received it |
  | `missing_in_platform` | High | Bank received it — platform has no record |
  | `amount_mismatch` | Medium | Both sides saw it; amounts differ (fees, FX rounding) |
  | `date_mismatch` | Low | Same transaction, different settlement dates |
  | `duplicate_platform` | Medium | Platform booked it twice |
  | `reversed_bank` | High | Bank reversed it — platform still shows it live |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data generation | Python 3.11 + `faker` + `random` (stdlib) |
| Reconciliation engine | Python + `pandas` (optional; pure-dict fallback included) |
| API | Flask 3 (serverless via Vercel Python runtime) |
| Frontend | Vanilla HTML / CSS / JS (zero frameworks, zero build step) |
| Deployment | Vercel (static + serverless, single `vercel.json`) |

---

## Implementation Steps

### Local Dev

```bash
# 1. Clone and install
git clone <your-repo>
cd ledger-lens
pip install -r requirements.txt

# 2. Run API
python api/index.py          # Flask dev server → http://localhost:5000

# 3. Open frontend
open public/index.html       # or serve with any static file server
# The HTML calls /api/reconcile relative to origin — works once deployed.
# For local dev point the fetch URL to http://localhost:5000/api/reconcile
```

### Deploy to Vercel

```bash
npm i -g vercel    # install Vercel CLI once
vercel             # follow prompts — auto-detects vercel.json
# Done. Live URL printed in terminal.
```

No environment variables required. No database. No external APIs.

---

## What This System Gets Wrong in Production

In production, transaction IDs are rarely stable across systems — payment processors, gateways, and banks each assign their own reference numbers, so the `txn_id` join key used here would collapse into a fuzzy-matching problem requiring ML or rule-based entity resolution. This engine treats amounts as final figures, ignoring that real payments travel through interchange fees, FX spreads, and acquirer charges that legitimately alter the amount at each hop, meaning many "mismatches" flagged here would be expected and correct. Finally, synthetic data has no temporal skew, weekend settlement delays, or cut-off timezone ambiguities — the date-mismatch detector would generate enormous false-positive noise against a real bank feed where T+2 settlement is the norm, not an anomaly.
