from collections import Counter

LABELS = ("scam", "suspicious", "legit")


def summarize(rows: list[dict]) -> dict:
    """rows: dicts with gold, pred (None on error), cost_usd, latency_s."""
    ok = [r for r in rows if r["pred"] is not None]
    by_gold = lambda g: [r for r in ok if r["gold"] == g]
    scams, legits = by_gold("scam"), by_gold("legit")
    confusion = Counter((r["gold"], r["pred"]) for r in ok)
    return {
        "n": len(rows),
        "errors": len(rows) - len(ok),
        "accuracy": _ratio(sum(r["gold"] == r["pred"] for r in ok), len(ok)),
        # Scams the app labels "scam" outright.
        "scam_recall": _ratio(sum(r["pred"] == "scam" for r in scams), len(scams)),
        # Scams the app lets through as "legit": the worst failure for users.
        "scam_miss_rate": _ratio(sum(r["pred"] == "legit" for r in scams), len(scams)),
        # Legit messages flagged as scam or suspicious: the cost of crying wolf.
        "legit_fp_rate": _ratio(sum(r["pred"] != "legit" for r in legits), len(legits)),
        "cost_usd": round(sum(r.get("cost_usd", 0) for r in rows), 4),
        "mean_latency_s": round(sum(r.get("latency_s", 0) for r in ok) / len(ok), 2) if ok else None,
        "confusion": {f"{g}->{p}": confusion[(g, p)] for g in LABELS for p in LABELS},
    }


def passes(summary: dict, min_scam_recall: float = 0.90, max_legit_fp: float = 0.10) -> bool:
    return summary["errors"] == 0 and summary["scam_recall"] >= min_scam_recall and summary["legit_fp_rate"] <= max_legit_fp


def _ratio(a: int, b: int) -> float:
    return round(a / b, 3) if b else 0.0
