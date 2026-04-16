"""
reconcile.py — core reconciliation engine
Generates synthetic ledger + bank data, finds gaps, returns structured results.
"""
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib

try:
    from faker import Faker
    HAS_FAKER = True
except ImportError:
    HAS_FAKER = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

CURRENCIES = ["USD", "EUR", "GBP", "INR", "SGD"]
MERCHANTS = [
    "Acme Retail", "ByteShop", "CloudPay Ltd", "DeltaMart",
    "EasyFoods", "FintechX", "GigStore", "HorizonTech",
    "IndigoBooks", "JetCommerce",
]

GAP_TYPES = {
    "missing_in_bank":    "Platform recorded it — bank never got it",
    "missing_in_platform":"Bank received it — platform has no record",
    "amount_mismatch":    "Both sides saw it but amounts differ (FX rounding, fees)",
    "date_mismatch":      "Same transaction, different settlement dates",
    "duplicate_platform": "Platform booked it twice",
    "reversed_bank":      "Bank reversed/refunded — platform still shows it",
}


def _amount(lo=10.0, hi=50_000.0):
    return float(Decimal(str(random.uniform(lo, hi))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _txn_id(n):
    return "TXN" + hashlib.md5(str(n + RANDOM_SEED).encode()).hexdigest()[:10].upper()

def _date_range(start="2024-03-01", days=31):
    base = datetime.strptime(start, "%Y-%m-%d")
    return base + timedelta(days=random.randint(0, days - 1))


def generate_dataset(n_clean=120, n_gaps=30):
    """
    Returns:
        platform_ledger : list[dict]
        bank_statement  : list[dict]
        injected_gaps   : list[dict]   — ground truth for UI
    """
    platform, bank, gaps = [], [], []
    gap_pool = list(GAP_TYPES.keys())

    # --- clean matching transactions ---
    for i in range(n_clean):
        txn_id  = _txn_id(i)
        amt     = _amount()
        date    = _date_range()
        merchant= random.choice(MERCHANTS)
        ccy     = random.choice(CURRENCIES)

        platform.append({"txn_id": txn_id, "amount": amt, "currency": ccy,
                         "date": date.strftime("%Y-%m-%d"), "merchant": merchant,
                         "source": "platform"})
        bank.append({"txn_id": txn_id, "amount": amt, "currency": ccy,
                     "date": date.strftime("%Y-%m-%d"), "merchant": merchant,
                     "source": "bank"})

    # --- inject anomalies ---
    for j in range(n_gaps):
        gap_type = gap_pool[j % len(gap_pool)]
        txn_id   = _txn_id(n_clean + j)
        amt      = _amount()
        date     = _date_range()
        merchant = random.choice(MERCHANTS)
        ccy      = random.choice(CURRENCIES)
        base     = {"txn_id": txn_id, "amount": amt, "currency": ccy,
                    "date": date.strftime("%Y-%m-%d"), "merchant": merchant}

        gap_record = {"txn_id": txn_id, "gap_type": gap_type,
                      "description": GAP_TYPES[gap_type], "currency": ccy,
                      "merchant": merchant, "date": date.strftime("%Y-%m-%d")}

        if gap_type == "missing_in_bank":
            platform.append({**base, "source": "platform"})
            gap_record["platform_amount"] = amt
            gap_record["bank_amount"]     = None

        elif gap_type == "missing_in_platform":
            bank.append({**base, "source": "bank"})
            gap_record["platform_amount"] = None
            gap_record["bank_amount"]     = amt

        elif gap_type == "amount_mismatch":
            bank_amt = round(amt * random.uniform(0.97, 1.03), 2)
            platform.append({**base, "source": "platform"})
            bank.append({**base, "amount": bank_amt, "source": "bank"})
            gap_record["platform_amount"] = amt
            gap_record["bank_amount"]     = bank_amt
            gap_record["delta"]           = round(bank_amt - amt, 2)

        elif gap_type == "date_mismatch":
            offset = random.choice([-2, -1, 1, 2])
            bank_date = (date + timedelta(days=offset)).strftime("%Y-%m-%d")
            platform.append({**base, "source": "platform"})
            bank.append({**base, "date": bank_date, "source": "bank"})
            gap_record["platform_amount"] = amt
            gap_record["bank_amount"]     = amt
            gap_record["platform_date"]   = base["date"]
            gap_record["bank_date"]       = bank_date

        elif gap_type == "duplicate_platform":
            platform.append({**base, "source": "platform"})
            platform.append({**base, "txn_id": txn_id + "_DUP", "source": "platform"})
            bank.append({**base, "source": "bank"})
            gap_record["platform_amount"] = amt * 2
            gap_record["bank_amount"]     = amt

        elif gap_type == "reversed_bank":
            platform.append({**base, "source": "platform"})
            bank.append({**base, "amount": -amt, "source": "bank"})
            gap_record["platform_amount"] = amt
            gap_record["bank_amount"]     = -amt

        gaps.append(gap_record)

    random.shuffle(platform)
    random.shuffle(bank)
    return platform, bank, gaps


def run_reconciliation(platform, bank):
    """
    Match platform vs bank by txn_id, surface every discrepancy.
    Returns dict of summary + findings.
    """
    p_map = {}
    for r in platform:
        tid = r["txn_id"]
        p_map.setdefault(tid, []).append(r)

    b_map = {}
    for r in bank:
        tid = r["txn_id"]
        b_map.setdefault(tid, []).append(r)

    all_ids = set(p_map) | set(b_map)
    findings = []

    for tid in all_ids:
        p_rows = p_map.get(tid, [])
        b_rows = b_map.get(tid, [])

        if p_rows and not b_rows:
            for r in p_rows:
                findings.append({**r, "issue": "missing_in_bank",
                                  "severity": "high",
                                  "detail": "No matching bank entry"})

        elif b_rows and not p_rows:
            for r in b_rows:
                findings.append({**r, "issue": "missing_in_platform",
                                  "severity": "high",
                                  "detail": "No platform record found"})

        else:
            # both sides present — check amounts & dates
            if len(p_rows) > 1:
                for r in p_rows:
                    findings.append({**r, "issue": "duplicate_platform",
                                      "severity": "medium",
                                      "detail": f"Appears {len(p_rows)}x on platform"})
                continue

            p, b = p_rows[0], b_rows[0]
            amt_diff = round(float(b["amount"]) - float(p["amount"]), 2)
            if abs(amt_diff) > 0.01:
                findings.append({**p, "issue": "amount_mismatch",
                                  "severity": "medium",
                                  "detail": f"Δ {amt_diff:+.2f} {p['currency']}"})

            if p["date"] != b["date"]:
                findings.append({**p, "issue": "date_mismatch",
                                  "severity": "low",
                                  "detail": f"Platform:{p['date']} Bank:{b['date']}"})

            if float(b["amount"]) < 0 < float(p["amount"]):
                findings.append({**p, "issue": "reversed_bank",
                                  "severity": "high",
                                  "detail": "Bank shows reversal/refund"})

    # --- summary ---
    p_total = sum(float(r["amount"]) for r in platform)
    b_total = sum(float(r["amount"]) for r in bank)

    issue_counts = {}
    for f in findings:
        issue_counts[f["issue"]] = issue_counts.get(f["issue"], 0) + 1

    return {
        "summary": {
            "platform_txn_count":  len(platform),
            "bank_txn_count":      len(bank),
            "platform_total":      round(p_total, 2),
            "bank_total":          round(b_total, 2),
            "net_discrepancy":     round(b_total - p_total, 2),
            "total_gaps_found":    len(findings),
            "gap_breakdown":       issue_counts,
        },
        "findings": findings,
    }


def full_report():
    platform, bank, _ = generate_dataset()
    return run_reconciliation(platform, bank)
